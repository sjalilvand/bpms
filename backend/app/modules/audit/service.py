# -*- coding: utf-8 -*-
"""ممیزی: رویدادهای قابل ممیزی — سوابق از مسیرهای عادی API قابل ویرایش نیستند."""
from datetime import datetime

from sqlalchemy import String, ForeignKey, Text, DateTime, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.identity.models import utcnow


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    detail_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


def log_action(db, user_id: int | None, action: str, entity: str | None = None,
               entity_id: int | None = None, detail: dict | None = None, request=None):
    """ثبت رویداد ممیزی — خطا در ثبت ممیزی نباید عملیات اصلی را متوقف کند."""
    try:
        ip = None
        if request is not None:
            ip = request.client.host if request.client else None
        db.add(AuditLog(user_id=user_id, action=action, entity=entity, entity_id=entity_id,
                        detail_json=detail or {}, ip=ip))
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
