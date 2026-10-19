# -*- coding: utf-8 -*-
"""اعلان داخل سامانه (پیامک/ایمیل در فاز بعدی از طریق اتصال قابل تنظیم)."""
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.core.database import Base
from app.modules.identity.models import utcnow, User, Role
from sqlalchemy import select


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


def notify_user(db: Session, user_id: int | None, title: str, body: str = "", link: str | None = None):
    if not user_id:
        return
    db.add(Notification(user_id=user_id, title=title[:200], body=body, link=link))


def notify_role(db: Session, role_code: str | None, title: str, body: str = "", link: str | None = None):
    if not role_code:
        return
    role = db.scalar(select(Role).where(Role.code == role_code))
    if not role:
        return
    for u in role.users:
        if u.is_active:
            db.add(Notification(user_id=u.id, title=title[:200], body=body, link=link))
