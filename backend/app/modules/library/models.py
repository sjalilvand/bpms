# -*- coding: utf-8 -*-
"""مدل‌های بانک سازمانی (فاز ۸):

- OrgField: فیلد استاندارد سازمانی — قابل استفاده در همه فرم‌سازها (کلید/برچسب/نوع/تنظیمات)
- FormTemplate: بانک فرم‌های سازمانی — الگوی آماده برای ساخت سریع فرم جدید
- ProcessTemplate: بانک فرایندهای سازمانی — الگوی BPMN آماده برای ساخت سریع فرایند جدید
"""
from datetime import datetime

from sqlalchemy import String, ForeignKey, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.identity.models import utcnow


class OrgField(Base):
    __tablename__ = "org_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(40), index=True)
    category: Mapped[str | None] = mapped_column(String(80), default="")
    description: Mapped[str | None] = mapped_column(Text, default="")
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)  # required/help/options/...
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FormTemplate(Base):
    __tablename__ = "form_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default="")
    category: Mapped[str | None] = mapped_column(String(80), default="", index=True)
    schema_json: Mapped[dict] = mapped_column(JSON)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProcessTemplate(Base):
    __tablename__ = "process_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default="")
    category: Mapped[str | None] = mapped_column(String(80), default="", index=True)
    bpmn_xml: Mapped[str] = mapped_column(Text)
    main_process_id: Mapped[str | None] = mapped_column(String(120), default="")
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
