# -*- coding: utf-8 -*-
"""فاز ۵/۶ — ارسال Webhook خروجی با الگوی انتشار پس از commit.

استفاده در سرویس موتور: queue_webhook(db, "instance.completed", {...})
- ثبت رویداد روی نشست (بدون I/O)
- پس از commit موفق: برای هر مقصد فعالِ مشترک، ردیف WebhookDelivery ساخته و
  ارسال انجام می‌شود با امضای HMAC.
- با rollback رویدادها دور ریخته می‌شوند (هیچ Webhook کاذبی برای تراکنش ناموفق نمی‌رود).

فاز ۶ — صف توزیع‌شده:
- در SCHEDULER_MODE=celery، ارسال هر ردیف به‌صورت تسک «bpms.webhooks.deliver»
  روی صف Celery (Redis) توزیع می‌شود؛ retry با backoff نمایی، acks_late و
  تسک «bpms.webhooks.sweep» ردیف‌های pending یتیم (سقوط Worker) را بازیابی می‌کند.
- در حالت inprocess (توسعه/پایلوت و آزمون‌ها) مسیر نخ پس‌زمینه همان رفتار پیشین است.
"""
from __future__ import annotations

import threading
import time
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, event
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.external.models import WebhookDelivery, WebhookEndpoint
from app.modules.external.service import safe_json_bytes, webhook_signature

logger = logging.getLogger("bpms.webhooks")

PENDING_WEBHOOKS = "bpms_pending_webhooks"
DELIVERY_TIMEOUT = 5.0
DELIVERY_RETRIES = 2          # مسیر نخ پس‌زمینه (تلاش‌های اضافی درون همان نخ)
WEBHOOK_MAX_ATTEMPTS = 5      # فاز ۶ — سقف کل تلاش‌ها در صف توزیع‌شده
SWEEP_STALE_MINUTES = 10      # ردیف pending قدیمی‌تر از این = یتیم


class TransientDeliveryFailure(Exception):
    """شکست موقت ارسال — Worker صف باید با backoff دوباره تلاش کند."""


def queue_webhook(db: Session, event_type: str, payload: dict) -> None:
    try:
        pending = db.info.setdefault(PENDING_WEBHOOKS, [])
        pending.append({"type": event_type, "data": payload or {},
                        "ts": datetime.now(timezone.utc).isoformat()})
    except Exception:
        pass


def _drain(session: Session):
    try:
        return session.info.pop(PENDING_WEBHOOKS, [])
    except Exception:
        return []


def _endpoints_for(db: Session, event_type: str) -> list[WebhookEndpoint]:
    rows = db.scalars(select(WebhookEndpoint).where(WebhookEndpoint.is_active.is_(True))).all()
    return [e for e in rows if "*" in (e.events or []) or event_type in (e.events or [])]


def _create_deliveries(ev: dict) -> list[tuple[int, str, str]]:
    """ثبت ردیف‌های تحویل (pending) در نشست کوتاه‌عمر — مشترک میان دو مسیر."""
    from app.core.database import SessionLocal
    jobs: list[tuple[int, str, str]] = []
    db = SessionLocal()
    try:
        for ep in _endpoints_for(db, ev["type"]):
            delivery = WebhookDelivery(endpoint_id=ep.id, event_type=ev["type"],
                                       payload_json=ev["data"], status="pending")
            db.add(delivery)
            db.flush()
            jobs.append((delivery.id, ep.url, ep.secret))
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("webhook delivery enqueue error: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
        return []
    finally:
        db.close()
    return jobs


def _deliver_single(delivery_id: int) -> dict:
    """یک تلاش HTTP برای ردیف تحویل ذخیره‌شده (مسیر صف توزیع‌شده — فاز ۶).

    - موفق → وضعیت success و delivered_at
    - شکست با سهم تلاش باقی‌مانده → وضعیت pending می‌ماند و TransientDeliveryFailure
      برمی‌خیزد تا Worker با backoff دوباره تلاش کند
    - شکست با اتمام سهم → وضعیت failed
    """
    import httpx
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        d = db.get(WebhookDelivery, delivery_id)
        if d is None:
            return {"ok": False, "gone": True}
        if d.status == "success":
            return {"ok": True, "skipped": True}
        ep = db.get(WebhookEndpoint, d.endpoint_id)
        if not ep or not ep.url:
            d.status = "failed"
            d.last_error = "مقصد Webhook یافت نشد/غیرفعال است"
            db.commit()
            return {"ok": False, "exhausted": True}
        body = safe_json_bytes({"event": d.event_type,
                                "ts": datetime.now(timezone.utc).isoformat(),
                                "data": d.payload_json})
        ts = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "X-BPMS-Event": d.event_type,
            "X-BPMS-Timestamp": ts,
            "X-BPMS-Signature": webhook_signature(ep.secret, ts, body),
        }
        status_code, err = None, None
        try:
            with httpx.Client(timeout=DELIVERY_TIMEOUT, verify=True) as client:
                resp = client.post(ep.url, content=body, headers=headers)
            status_code = resp.status_code
            err = None if resp.status_code < 400 else f"پاسخ {resp.status_code}"
        except Exception as e:  # noqa: BLE001
            err = str(e)[:300]
        d.attempts = (d.attempts or 0) + 1
        d.last_status_code = status_code
        d.last_error = err
        if status_code is not None and status_code < 400:
            d.status = "success"
            d.delivered_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
            return {"ok": True, "attempts": d.attempts}
        if (d.attempts or 0) >= WEBHOOK_MAX_ATTEMPTS:
            d.status = "failed"
            db.commit()
            return {"ok": False, "exhausted": True, "attempts": d.attempts}
        db.commit()
        raise TransientDeliveryFailure(err or "خطای ناشناخته در ارسال Webhook")
    finally:
        db.close()


def _deliver(ev: dict) -> None:
    """مسیر نخ پس‌زمینه (inprocess) — ارسال در نشست‌های کوتاه‌عمر مستقل."""
    import httpx

    jobs = _create_deliveries(ev)
    if not jobs:
        return

    # فراخوانی HTTP بدون تراکنش باز
    results: dict[int, tuple] = {}
    for delivery_id, url, secret in jobs:
        body = safe_json_bytes({"event": ev["type"], "ts": ev["ts"], "data": ev["data"]})
        status_code, err, attempts = None, None, 0
        for attempt in range(DELIVERY_RETRIES + 1):
            attempts = attempt + 1
            ts = str(int(time.time()))
            headers = {
                "Content-Type": "application/json",
                "X-BPMS-Event": ev["type"],
                "X-BPMS-Timestamp": ts,
                "X-BPMS-Signature": webhook_signature(secret, ts, body),
            }
            try:
                with httpx.Client(timeout=DELIVERY_TIMEOUT, verify=True) as client:
                    resp = client.post(url, content=body, headers=headers)
                status_code = resp.status_code
                if resp.status_code < 400:
                    err = None
                    break
                err = f"پاسخ {resp.status_code}"
            except Exception as e:  # noqa: BLE001
                err = str(e)[:300]
            if attempt < DELIVERY_RETRIES:
                time.sleep(0.5 * (attempt + 1))
        results[delivery_id] = (status_code, err, attempts)

    # به‌روزرسانی گزارش تحویل در نشست جدید
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        for delivery_id, (status_code, err, attempts) in results.items():
            d = db.get(WebhookDelivery, delivery_id)
            if not d:
                continue
            d.attempts = attempts
            d.last_status_code = status_code
            d.last_error = err
            d.status = "success" if (status_code and status_code < 400) else "failed"
            if d.status == "success":
                d.delivered_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("webhook delivery finalize error: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def _dispatch_via_celery(ev: dict) -> bool:
    """فاز ۶ — توزیع ارسال روی صف Celery. True یعنی مسیر صف در دست گرفته است."""
    if ((settings.SCHEDULER_MODE or "inprocess").lower() != "celery"):
        return False
    try:
        from app.worker.celery_app import celery_app
        if celery_app is None:
            return False
        jobs = _create_deliveries(ev)
        for delivery_id, _url, _secret in jobs:
            celery_app.send_task("bpms.webhooks.deliver", args=[delivery_id])
        return True  # حتی در شکست نیمه‌راه، sweeper ردیف‌های pending را بازیابی می‌کند
    except Exception as e:  # noqa: BLE001
        logger.warning("dispatch به صف Celery ناموفق بود (fallback به نخ): %s", e)
        return False


def sweep_stale_deliveries(stale_minutes: int = SWEEP_STALE_MINUTES) -> dict:
    """بازیابی ردیف‌های pending یتیم — فاز ۶ (beat هر ۵ دقیقه).

    - pending قدیمی‌تر از stale_minutes با سهم تلاش باقی‌مانده → دوباره به صف می‌رود
    - pending با سهم اتمام‌شده → failed
    """
    from app.core.database import SessionLocal

    db = SessionLocal()
    ids: list[int] = []
    marked_failed = 0
    try:
        threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=stale_minutes)
        rows = db.scalars(select(WebhookDelivery).where(
            WebhookDelivery.status == "pending",
            WebhookDelivery.created_at < threshold)).all()
        for d in rows:
            if (d.attempts or 0) >= WEBHOOK_MAX_ATTEMPTS:
                d.status = "failed"
                d.last_error = d.last_error or "انقضای صف — حداکثر تلاش‌ها به پایان رسید"
                marked_failed += 1
            else:
                ids.append(d.id)
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("webhook sweep query error: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
        return {"redispatched": 0, "marked_failed": 0, "error": str(e)[:200]}
    finally:
        db.close()

    redispatched = 0
    if ids:
        try:
            from app.worker.celery_app import celery_app
            if celery_app is not None:
                for i in ids:
                    celery_app.send_task("bpms.webhooks.deliver", args=[i])
                    redispatched += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("webhook sweep redispatch error: %s", e)
    return {"redispatched": redispatched, "marked_failed": marked_failed}


@event.listens_for(Session, "after_commit")
def _dispatch_after_commit(session: Session) -> None:
    for ev in _drain(session):
        if not _dispatch_via_celery(ev):
            threading.Thread(target=_deliver, args=(ev,), daemon=True).start()


@event.listens_for(Session, "after_soft_rollback")
def _clear_on_rollback(session: Session, transaction) -> None:  # pragma: no cover
    _drain(session)


@event.listens_for(Session, "after_rollback")
def _clear_after_rollback(session: Session) -> None:  # pragma: no cover
    _drain(session)
