# -*- coding: utf-8 -*-
"""فاز ۵ — ارسال Webhook خروجی با الگوی انتشار پس از commit.

استفاده در سرویس موتور: queue_webhook(db, "instance.completed", {...})
- ثبت رویداد روی نشست (بدون I/O)
- پس از commit موفق: برای هر مقصد فعالِ مشترک، ردیف WebhookDelivery ساخته و
  ارسال در نخ پس‌زمینه انجام می‌شود (timeout و retry محدود، امضای HMAC).
- با rollback رویدادها دور ریخته می‌شوند (هیچ Webhook کاذبی برای تراکنش ناموفق نمی‌رود).
"""
from __future__ import annotations

import threading
import time
import logging
from datetime import datetime, timezone

from sqlalchemy import select, event
from sqlalchemy.orm import Session

from app.modules.external.models import WebhookDelivery, WebhookEndpoint
from app.modules.external.service import safe_json_bytes, webhook_signature

logger = logging.getLogger("bpms.webhooks")

PENDING_WEBHOOKS = "bpms_pending_webhooks"
DELIVERY_TIMEOUT = 5.0
DELIVERY_RETRIES = 2


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


def _deliver(ev: dict) -> None:
    """ارسال در نشست‌های کوتاه‌عمر مستقل — HTTP خارج از تراکنش تا قفل DB رخ ندهد."""
    import httpx
    from app.core.database import SessionLocal

    # ۱) ثبت ردیف‌های تحویل (pending) و بستن سریع نشست
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
        db.close()
        return
    db.close()

    # ۲) فراخوانی HTTP بدون تراکنش باز
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

    # ۳) به‌روزرسانی گزارش تحویل در نشست جدید
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


@event.listens_for(Session, "after_commit")
def _dispatch_after_commit(session: Session) -> None:
    for ev in _drain(session):
        threading.Thread(target=_deliver, args=(ev,), daemon=True).start()


@event.listens_for(Session, "after_soft_rollback")
def _clear_on_rollback(session: Session, transaction) -> None:  # pragma: no cover
    _drain(session)


@event.listens_for(Session, "after_rollback")
def _clear_after_rollback(session: Session) -> None:  # pragma: no cover
    _drain(session)
