# -*- coding: utf-8 -*-
"""کاتالوگ کانکتورها — فراخوانی سرویس کنترل‌شده (سند §۲۰).

انواع مجاز در این نسخه:
- mock:<name>   → سرویس‌های آزمایشی داخلی (ثبت سفارش و ...)
- http:<METHOD>:<URL> → فراخوانی REST با timeout و retry محدود
- dmn:<decisionKey>  → ارزیابی جدول تصمیم (فاز ۳) و ادغام خروجی در متغیرها

قرارداد: داده ورودی از متغیرهای فرایند؛ پاسخ dict به متغیرهای فرایند ادغام می‌شود.
خطا با بازگشت False → فعالیت در حالت ERROR و ایجاد Incident (AC-15).
هیچ اجرای آزاد کد از این مسیر انجام نمی‌شود.
"""
from __future__ import annotations

import json
import time
import logging

import httpx

logger = logging.getLogger("bpms.connectors")

HTTP_TIMEOUT = 10.0
HTTP_RETRIES = 2
MAX_PAYLOAD_KEYS = 200

MOCK_CONNECTORS = {
    "register_order": lambda data: {"order_id": f"SO-{int(time.time())}", "order_status": "registered"},
    "echo": lambda data: {"echo": {k: data.get(k) for k in list(data)[:10]}},
    "notify": lambda data: {"notified": True},
}


def _sanitize(data: dict) -> dict:
    """پوشاندن اطلاعات حساس در لاگ."""
    return {k: ("***" if any(s in k.lower() for s in ("password", "token", "secret")) else v)
            for k, v in list(data.items())[:MAX_PAYLOAD_KEYS]}


def _current_db():
    """نشست کوتاه‌عمر برای کانکتورهایی که به پایگاه نیاز دارند (مانند dmn:)."""
    from app.core.database import SessionLocal
    return SessionLocal()


def _run_dmn(key: str, data: dict):
    """ارزیابی جدول تصمیم با نشست کوتاه‌عمر (فاز ۳)."""
    from app.modules.decisions import service as dsvc
    from app.modules.decisions.engine import DecisionError
    if not key:
        raise RuntimeError("کلید جدول تصمیم مشخص نشده است")
    inputs = {k: v for k, v in (data or {}).items() if not k.startswith("_")}
    db = _current_db()
    try:
        return dsvc.evaluate_by_key(db, key, inputs)
    except DecisionError as e:
        raise RuntimeError(f"خطای ارزیابی جدول تصمیم: {e}")
    finally:
        db.close()


def execute_connector(task, spec) -> bool:
    """اجرای فعالیت سیستمی؛ False یعنی خطا → فعالیت ERROR + Incident."""
    impl = (getattr(spec, "description", "") or "") + " " + str(getattr(spec, "bpmn_id", "") or "")
    # قرارداد: در تنظیمات فعالیت، شناسه کانکتور در متغیر فرایند _connectors ذخیره می‌شود
    # یا مستقیماً از نام فنی عنصر: connector در binding فرایند.
    connector_ref = None
    data = task.data or {}
    connectors = data.get("_connectors") or {}
    if isinstance(connectors, dict):
        connector_ref = connectors.get(spec.name)
    if not connector_ref:
        # fallback: متغیر _connector_default
        connector_ref = data.get("_connector_default")
    if not connector_ref:
        logger.error("connector not configured for %s", spec.name)
        task.data.setdefault("_last_connector_error", f"کانکتوری برای «{spec.name}» تنظیم نشده است")
        return False

    try:
        result = _run(connector_ref, data)
        if isinstance(result, dict):
            for k, v in result.items():
                if not k.startswith("_"):
                    task.data[k] = v
        task.data["_last_connector_result"] = "ok"
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("connector %s failed: %s", connector_ref, e)
        task.data["_last_connector_error"] = str(e)[:500]
        task.data["_last_connector_result"] = "failed"
        return False


def _run(ref: str, data: dict):
    kind, _, rest = ref.partition(":")
    if kind == "mock":
        fn = MOCK_CONNECTORS.get(rest)
        if not fn:
            raise RuntimeError(f"کانکتور آزمایشی «{rest}» تعریف نشده است")
        return fn(_sanitize(data))
    if kind == "dmn":
        # فاز ۳: ارزیابی جدول تصمیم منتشرشده — داده ورودی = متغیرهای فرایند
        return _run_dmn(rest, data)
    if kind == "http":
        # فرمت: http:METHOD:URL  — بدنه از متغیرهای فرایند ساخته می‌شود
        method, _, url = rest.partition(":")
        if not url:
            raise RuntimeError("آدرس سرویس مشخص نشده است")
        body = {k: v for k, v in _sanitize(data).items() if not k.startswith("_")}
        last_err = None
        for attempt in range(HTTP_RETRIES + 1):
            try:
                with httpx.Client(timeout=HTTP_TIMEOUT, verify=True) as client:
                    resp = client.request(method.upper() or "POST", url, json=body)
                if resp.status_code >= 400:
                    raise RuntimeError(f"پاسخ {resp.status_code} از سرویس")
                try:
                    return resp.json()
                except json.JSONDecodeError:
                    return {"response_text": resp.text[:1000]}
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < HTTP_RETRIES:
                    time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"فراخوانی سرویس ناموفق بود: {last_err}")
    raise RuntimeError(f"نوع کانکتور «{kind}» پشتیبانی نمی‌شود")
