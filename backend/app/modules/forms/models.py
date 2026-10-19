# -*- coding: utf-8 -*-
"""مدل‌های فرم: تعریف، نسخه (Schema)، ثبت داده."""
from datetime import datetime

from sqlalchemy import String, ForeignKey, Text, DateTime, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.identity.models import utcnow


class FormDefinition(Base):
    __tablename__ = "form_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    versions: Mapped[list["FormVersion"]] = relationship(back_populates="form", lazy="selectin", order_by="FormVersion.version.desc()")

    @property
    def latest_published(self) -> "FormVersion | None":
        for v in self.versions:
            if v.status == "published":
                return v
        return None


class FormVersion(Base):
    __tablename__ = "form_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    form_id: Mapped[int] = mapped_column(ForeignKey("form_definitions.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    schema_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)  # draft | published | archived
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    change_note: Mapped[str | None] = mapped_column(String(300), default="")

    form: Mapped[FormDefinition] = relationship(back_populates="versions")


class FormSubmission(Base):
    """ثبت داده فرم — پاسخ به‌صورت JSON نسخه‌بندی‌شده نگهداری می‌شود (مدل ترکیبی سند §۲۶.۲)."""
    __tablename__ = "form_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    form_version_id: Mapped[int | None] = mapped_column(ForeignKey("form_versions.id", ondelete="SET NULL"), index=True)
    instance_id: Mapped[int | None] = mapped_column(index=True)
    task_id: Mapped[int | None] = mapped_column(index=True)
    data_json: Mapped[dict] = mapped_column(JSON)
    submitted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="final")  # draft | final
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
