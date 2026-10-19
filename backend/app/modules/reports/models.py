# -*- coding: utf-8 -*-
"""فاز ۶ — مدل گزارش ذخیره‌شده: پیکربندی قابل استفاده مجدد از گزارش‌ساز/KPI."""
from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base
from app.modules.identity.models import utcnow


class SavedReport(Base):
    """گزارش ذخیره‌شده — داده‌کاوی قابل تکرار روی شاخص‌ها.

    definition نمونه:
        {"dataset": "overview" | "bottlenecks" | "workload" | "volume",
         "filters": {"days": 30, "date_from": null, "date_to": null,
                     "definition_id": null, "status": null}}
    """
    __tablename__ = "saved_reports"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, default="")
    dataset = Column(String(40), nullable=False)            # نوع مجموعه‌داده KPI
    definition = Column(JSON, default=dict, nullable=False)  # فیلترهای ذخیره‌شده
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
