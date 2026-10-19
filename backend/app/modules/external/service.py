# -*- coding: utf-8 -*-
"""فاز ۵ — سرویس API بیرونی: احراز کلید + امضای HMAC، محدودیت نرخ و idempotency.

قرارداد فراخوانی بیرونی (سند §۳۳):
- هدر X-API-Key: شناسه کلید سرویس
- هدر X-Timestamp: ثانیه یونیکس (تلورانس ±۳۰۰ ثانیه — مقابله با بازپخش)
- هدر X-Signature: hex HMAC-SHA256(secret, f"{timestamp}.{raw_body}") — اگر require_signature
- هدر Idempotency-Key: برای عملیات نوشتاری — پاسخ همان درخواست تکراری بازپخش می‌شود
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.external.models import ExternalClient, ExternalIdempotency

TIMESTAMP_TOLERANCE = 300  # ثانیه
IDEMPOTENCY_MAX_STORED = 5000  # سقف رکوردهای نگهداری‌شده در پاک‌سازی


def generate_client_credentials() -> tuple[str, str]:
    """تولید جفت (key_id, secret) — secret یک‌بار نمایش داده می‌شود."""
    key_id = "bpms_" + secrets.token_hex(8)
    secret = secrets.token_hex(24)
    return key_id, secret


def compute_signature(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), f"{timestamp}.".encode("utf-8") + body, hashlib.sha256).hexdigest()


def fingerprint(method: str, path: str, body: bytes) -> str:
    return hashlib.sha256(f"{method.upper()} {path} ".encode("utf-8") + body).hexdigest()


# ---------------- محدودیت نرخ درون‌حافظه‌ای (هر پروسه) ----------------
_RATE_BUCKETS: dict[int, deque] = defaultdict(deque)
_RATE_LOCK = threading.Lock()


def check_rate_limit(client: ExternalClient) -> None:
    now = time.time()
    limit = int(client.rate_limit_per_min or 60)
    with _RATE_LOCK:
        bucket = _RATE_BUCKETS[client.id]
        while bucket and bucket[0] < now - 60:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(429, "سقف فراخوانی سرویس بیرونی پر شده است (rate limit)")
        bucket.append(now)


# ---------------- احراز درخواست بیرونی ----------------
def authenticate(db: Session, request: Request, raw_body: bytes, required_scope: str) -> ExternalClient:
    key_id = request.headers.get("X-API-Key", "")
    if not key_id:
        raise HTTPException(401, "کلید API بیرونی ارسال نشده است (X-API-Key)")
    client = db.scalar(select(ExternalClient).where(ExternalClient.key_id == key_id))
    if not client or not client.is_active:
        raise HTTPException(401, "کلید API نامعتبر است")
    check_rate_limit(client)

    scopes = client.scopes or []
    if "*" not in scopes and required_scope not in scopes:
        raise HTTPException(403, f"دامنه مجاز این سرویس «{required_scope}» را شامل نمی‌شود")

    if client.require_signature:
        ts = request.headers.get("X-Timestamp", "")
        sig = request.headers.get("X-Signature", "")
        if not ts or not sig:
            raise HTTPException(401, "امضای درخواست (X-Signature/X-Timestamp) ارسال نشده است")
        try:
            if abs(time.time() - float(ts)) > TIMESTAMP_TOLERANCE:
                raise HTTPException(401, "مهلت اعتبار امضا گذشته است (replay)")
        except ValueError:
            raise HTTPException(401, "مهر زمانی نامعتبر است")
        expected = compute_signature(client.key_secret, ts, raw_body)
        if not hmac.compare_digest(expected, sig):
            raise HTTPException(401, "امضای درخواست نادرست است")

    client.last_used_at = __import__("datetime").datetime.utcnow()
    return client


# ---------------- idempotency ----------------
def lookup_idempotent(db: Session, client: ExternalClient, key: str, fp: str, endpoint: str):
    """اگر کلید تکراری باشد: پاسخ ذخیره‌شده بازپخش یا تعارض اعلام می‌شود."""
    if not key:
        return None
    if len(key) > 200:
        raise HTTPException(400, "طول Idempotency-Key حداکثر ۲۰۰ نویسه است")
    row = db.scalar(select(ExternalIdempotency).where(
        ExternalIdempotency.client_id == client.id,
        ExternalIdempotency.idempotency_key == key))
    if row is None:
        return None
    if row.request_fingerprint != fp:
        raise HTTPException(409, "این Idempotency-Key قبلاً برای درخواست دیگری استفاده شده است")
    return {"replay": True, "status": row.response_status, "body": row.response_json or {}}


def store_idempotent(db: Session, client: ExternalClient, key: str, fp: str,
                     endpoint: str, status: int, body: dict) -> None:
    if not key:
        return
    try:
        db.add(ExternalIdempotency(
            client_id=client.id, idempotency_key=key, endpoint=endpoint[:200],
            request_fingerprint=fp, response_status=status, response_json=body))
        db.flush()
        _prune_idempotency(db)
    except Exception:
        # مسابقه ثبت هم‌زمان همان کلید — به‌عنوان بازپخش با fingerprint فعلی اداره نمی‌شود؛ نادیده
        db.rollback()


def _prune_idempotency(db: Session) -> None:
    """نگهداشت سقف رکوردها (ساده: حذف قدیمی‌ترین‌ها فراتر از سقف)."""
    try:
        from sqlalchemy import func as _func, delete as _delete
        total = db.scalar(select(_func.count()).select_from(ExternalIdempotency)) or 0
        if total <= IDEMPOTENCY_MAX_STORED:
            return
        cutoff = total - IDEMPOTENCY_MAX_STORED
        old_ids = db.scalars(select(ExternalIdempotency.id).order_by(ExternalIdempotency.id).limit(cutoff)).all()
        if old_ids:
            db.execute(_delete(ExternalIdempotency).where(ExternalIdempotency.id.in_(old_ids)))
    except Exception:
        pass


# ---------------- ابزار امضای Webhook خروجی (مشترک با tests) ----------------
def webhook_signature(secret: str, timestamp: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"),
                                f"{timestamp}.".encode("utf-8") + body, hashlib.sha256).hexdigest()


def safe_json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
