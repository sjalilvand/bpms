# -*- coding: utf-8 -*-
"""مدل‌های جدول تصمیم (DMN سبک) — تعریف، نسخه، وضعیت انتشار.

ساختار schema_json هر نسخه:
{
  "hitPolicy": "FIRST|UNIQUE|ANY|PRIORITY|COLLECT",
  "inputs":  [{"name": "amount", "label": "مبلغ", "type": "number|string|boolean"}],
  "outputs": [{"name": "approvalLevel", "label": "سطح تأیید", "defaultValue": ...}],
  "rules":   [{"id": "...", "label": "...", "inputEntries": {"amount": "> 100"},
               "outputEntries": {"approvalLevel": "manager"}, "priority": 1, "enabled": True}]
}
- ورودی خالی («-») یعنی هر مقدار (Wildcard).
- عبارت ورودی از ارزیاب امن استفاده می‌کند؛ بدون eval/exec.
- نسخه منتشرشده تغییرناپذیر است؛ ویرایش همیشه نسخه جدید می‌سازد (قرارداد AC-14 فرایندها).
"""
from datetime import datetime

from sqlalchemy import String, ForeignKey, Text, DateTime, JSON, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.identity.models import utcnow

HIT_POLICIES = ("FIRST", "UNIQUE", "ANY", "PRIORITY", "COLLECT")


class DecisionDefinition(Base):
    __tablename__ = "decision_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    versions: Mapped[list["DecisionVersion"]] = relationship(
        back_populates="definition", lazy="selectin",
        order_by="DecisionVersion.version.desc()", cascade="all, delete-orphan")

    @property
    def latest_published(self) -> "DecisionVersion | None":
        for v in self.versions:
            if v.status == "published":
                return v
        return None


class DecisionVersion(Base):
    __tablename__ = "decision_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("decision_definitions.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)  # draft|published|archived
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    change_note: Mapped[str | None] = mapped_column(String(300), default="")

    definition: Mapped[DecisionDefinition] = relationship(back_populates="versions")
