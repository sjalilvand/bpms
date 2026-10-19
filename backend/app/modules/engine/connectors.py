# -*- coding: utf-8 -*-
"""کاتالوگ کانکتورها — فراخوانی سرویس کنترل‌شده (سند §۲۰).

انواع مجاز در این نسخه:
- mock:<name>   → سرویس‌های آزمایشی داخلی (ثبت سفارش و ...)
- http:<METHOD>:<URL> → فراخوانی REST با timeout و retry محدود
- dmn:<decisionKey>  → ارزیابی جدول تصمیم (فاز ۳) و ادغام خروجی در متغیرها
- soap:<URL>[|<SOAPAction>] → فراخوانی سرویس SOAP 1.1 (فاز ۵) — پارامترها از متغیرهای فرایند

قرارداد: داده ورودی از متغیرهای فرایند؛ پاسخ dict به متغیرهای فرایند ادغام می‌شود.
خطا با بازگشت False → فعالیت در حالت ERROR و ایجاد Incident (AC-15).
هیچ اجرای آزاد کد از این مسیر انجام نمی‌شود.
"""
from __future__ import annotations

import json
import re
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
    if kind == "soap":
        # فرمت: soap:URL|SOAPAction — جداکننده «|» تا با http:// در URL تداخل نکند (فاز ۵)
        url, _, action = rest.partition("|")
        if not url:
            raise RuntimeError("آدرس سرویس SOAP مشخص نشده است")
        return _run_soap(url, action, _sanitize(data))
    raise RuntimeError(f"نوع کانکتور «{kind}» پشتیبانی نمی‌شود")


# ---------------- SOAP 1.1 (فاز ۵) ----------------
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
SOAP_ARG_NS = "http://bpms.local/connector"


def _xml_escape(v: str) -> str:
    return (str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


def _soap_args(data: dict) -> str:
    """پارامترهای ساده به‌صورت عنصر؛ مقدار پیچیده JSON می‌شود — سقف ۵۰ پارامتر."""
    import json as _json
    parts = []
    for k, v in list((data or {}).items())[:50]:
        if not k or k.startswith("_"):
            continue
        tag = _xml_escape(re.sub(r"[^A-Za-z0-9_.-]", "_", str(k))[:60])
        val = v if isinstance(v, (str, int, float, bool)) else _json.dumps(v, ensure_ascii=False, default=str)
        parts.append(f"  <arg name=\"{tag}\">{_xml_escape(val)}</arg>")
    return "\n".join(parts)


def _build_envelope(data: dict) -> str:
    return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            f'<soapenv:Envelope xmlns:soapenv="{SOAP_NS}" xmlns:bpms="{SOAP_ARG_NS}">'
            "<soapenv:Header/><soapenv:Body>"
            '<bpms:execute>'
            f"{_soap_args(data)}"
            "</bpms:execute>"
            "</soapenv:Body></soapenv:Envelope>")


def _run_soap(url: str, action: str, data: dict):
    envelope = _build_envelope(data)
    headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{action or ""}"'}
    last_err = None
    for attempt in range(HTTP_RETRIES + 1):
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT, verify=True) as client:
                resp = client.post(url, content=envelope.encode("utf-8"), headers=headers)
            if resp.status_code >= 400:
                raise RuntimeError(f"پاسخ {resp.status_code} از سرویس SOAP")
            return _parse_soap_response(resp.text)
        except RuntimeError:
            raise
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < HTTP_RETRIES:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"فراخوانی SOAP ناموفق بود: {last_err}")


def _parse_soap_response(text: str) -> dict:
    """استخراج بدنه پاسخ؛ Fault → خطا؛ عناصر ساده بدنه به dict تبدیل می‌شود."""
    from lxml import etree
    try:
        root = etree.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    except etree.XMLSyntaxError as e:
        raise RuntimeError(f"پاسخ SOAP نامعتبر است: {e}")
    fault = root.find(f".//{{{SOAP_NS}}}Fault")
    if fault is not None:
        msg = fault.findtext(f".//{{{SOAP_NS}}}faultstring") or "خطای SOAP"
        raise RuntimeError(f"SOAP Fault: {msg[:300]}")
    body = root.find(f"{{{SOAP_NS}}}Body")
    out: dict = {}
    if body is not None:
        for el in body.iter():
            if not isinstance(el.tag, str):
                continue
            if el.tag.endswith("}Result"):
                out["result"] = el.text
                break
    if not out:
        out = {"response_text": (text or "")[:1000]}
    return out
