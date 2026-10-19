# -*- coding: utf-8 -*-
"""ساختار سازمانی: واحد سازمانی سلسله‌مراتبی + جانشینی."""
from datetime import datetime

from sqlalchemy import String, ForeignKey, Text, DateTime, Boolean, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.identity.models import utcnow


class OrganizationUnit(Base):
    __tablename__ = "organization_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    code: Mapped[str | None] = mapped_column(String(50), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("organization_units.id", ondelete="SET NULL"))
    description: Mapped[str | None] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    parent: Mapped["OrganizationUnit | None"] = relationship(remote_side=[id], lazy="selectin")
    children: Mapped[list["OrganizationUnit"]] = relationship(back_populates="parent", lazy="selectin")

    def to_tree(self):
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "parent_id": self.parent_id,
            "children": [c.to_tree() for c in (self.children or [])],
        }


class Delegation(Base):
    """جانشینی در بازه زمانی مشخص — وظایف کاربر اصلی در کارتابل جانشین نیز ظاهر می‌شود."""
    __tablename__ = "delegations"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    to_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    start_date: Mapped[datetime] = mapped_column(Date)
    end_date: Mapped[datetime] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
