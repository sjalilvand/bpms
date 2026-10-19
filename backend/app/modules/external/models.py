# -*- coding: utf-8 -*-
"""فاز ۵ — مدل‌های API بیرونی: کلید سرویس، idempotency، Webhook و تحویل رویداد."""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.core.database import Base
from app.modules.identity.models import utcnow


class ExternalClient(Base):
    """سرویس بیرونی مجاز به فراخوانی API سامانه با کلید (+ امضای اختیاری HMAC)."""
    __tablename__ = "external_clients"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    key_id = Column(String(64), unique=True, nullable=False, index=True)
    key_secret = Column(String(128), nullable=False)          # رمز امضا (سرور تولید می‌کند)
    scopes = Column(JSON, default=list, nullable=False)        # instances.start / instances.read / tasks.complete
    require_signature = Column(Boolean, default=False, nullable=False)
    rate_limit_per_min = Column(Integer, default=60, nullable=False)
    actor_username = Column(String(50), nullable=True)          # کاربر نماینده فراخوانی‌های این سرویس
    is_active = Column(Boolean, default=True, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)


class ExternalIdempotency(Base):
    """کلید idempotency برای عملیات نوشتاری بیرونی — پاسخ ذخیره و در تکرار بازپخش می‌شود."""
    __tablename__ = "external_idempotency"
    __table_args__ = (UniqueConstraint("client_id", "idempotency_key", name="uq_external_idem"),)

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("external_clients.id"), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    endpoint = Column(String(200), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)   # sha256(method+path+body)
    response_status = Column(Integer, nullable=False)
    response_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class WebhookEndpoint(Base):
    """مقصد Webhook — رویدادهای انتخابی با امضای HMAC-SHA256 ارسال می‌شود."""
    __tablename__ = "webhook_endpoints"

    id = Column(Integer, primary_key=True)
    url = Column(String(500), nullable=False)
    secret = Column(String(128), nullable=False)               # برای امضای خروجی
    events = Column(JSON, default=list, nullable=False)        # ["instance.completed", ...] یا ["*"]
    is_active = Column(Boolean, default=True, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class WebhookDelivery(Base):
    """گزارش تحویل هر رویداد — وضعیت، تلاش‌ها و آخرین پاسخ سرویس مقصد."""
    __tablename__ = "webhook_deliveries"

    id = Column(Integer, primary_key=True)
    endpoint_id = Column(Integer, ForeignKey("webhook_endpoints.id"), nullable=False)
    event_type = Column(String(80), nullable=False)
    payload_json = Column(JSON, nullable=True)
    status = Column(String(20), default="pending", nullable=False)   # pending/success/failed
    attempts = Column(Integer, default=0, nullable=False)
    last_status_code = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    delivered_at = Column(DateTime, nullable=True)
