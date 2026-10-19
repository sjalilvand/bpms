# -*- coding: utf-8 -*-
"""مدل‌های هویت و دسترسی: کاربر، نقش، مجوز (نقش‌محور با لیست مجوز صریح)."""
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Table, Column, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


user_role = Table(
    "user_role", Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)   # کد یکتا؛ به‌عنوان گروه نامزد نیز استفاده می‌شود
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, default="")
    permissions: Mapped[list] = mapped_column("permissions_json", __import__("sqlalchemy").JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    users: Mapped[list["User"]] = relationship(secondary=user_role, back_populates="roles")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(120))
    mobile: Mapped[str | None] = mapped_column(String(11))
    national_id: Mapped[str | None] = mapped_column(String(10))
    org_unit_id: Mapped[int | None] = mapped_column(ForeignKey("organization_units.id", ondelete="SET NULL"))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    roles: Mapped[list[Role]] = relationship(secondary=user_role, back_populates="users", lazy="selectin")
    org_unit: Mapped["OrganizationUnit | None"] = relationship("OrganizationUnit", foreign_keys=[org_unit_id], lazy="selectin")

    def role_codes(self) -> list[str]:
        return [r.code for r in self.roles]

    def to_dict_brief(self):
        return {
            "id": self.id,
            "username": self.username,
            "full_name": self.full_name,
            "org_unit_id": self.org_unit_id,
            "is_active": self.is_active,
        }
