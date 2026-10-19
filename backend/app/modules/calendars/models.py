# -*- coding: utf-8 -*-
"""مدل‌های تقویم کاری — تقویم، برنامه هفتگی، تعطیلات.

ساختار schedule_json (به وقت محلی تقویم):
{
  "monday":    {"enabled": false},
  "tuesday":   {"enabled": true, "start": "08:00", "end": "16:00",
                "breaks": [{"start": "12:00", "end": "13:00"}]},
  ...
}
- کلیدها: monday..sunday (شماره‌گذاری ISO: دوشنبه=0 ... یکشنبه=6)
- تعطیلات: تاریخ میلادی ذخیره می‌شود (تبدیل جلالی در رابط کاربری انجام می‌شود).
- yearly: تعطیلی تکرارشونده سالانه (مثلاً ۱ فروردین) — ماه/روز از تاریخ گرفته می‌شود.
"""
from datetime import datetime

from sqlalchemy import String, ForeignKey, Text, DateTime, JSON, Boolean, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.identity.models import utcnow

WEEKDAYS_FA = {
    "saturday": "شنبه", "sunday": "یکشنبه", "monday": "دوشنبه", "tuesday": "سه‌شنبه",
    "wednesday": "چهارشنبه", "thursday": "پنجشنبه", "friday": "جمعه",
}
DAY_KEYS = list(WEEKDAYS_FA.keys())  # ترتیب هفته ایرانی: شنبه تا جمعه


class WorkCalendar(Base):
    __tablename__ = "work_calendars"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text, default="")
    timezone: Mapped[str] = mapped_column(String(60), default="Asia/Tehran")
    schedule_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    holidays: Mapped[list["CalendarHoliday"]] = relationship(
        back_populates="calendar", lazy="selectin", cascade="all, delete-orphan")


class CalendarHoliday(Base):
    __tablename__ = "calendar_holidays"
    __table_args__ = (UniqueConstraint("calendar_id", "date", name="uq_calendar_holiday_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    calendar_id: Mapped[int] = mapped_column(ForeignKey("work_calendars.id", ondelete="CASCADE"), index=True)
    date: Mapped[datetime] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(200), default="")
    yearly: Mapped[bool] = mapped_column(Boolean, default=False)  # تعطیلی تکرارشونده سالانه
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    calendar: Mapped[WorkCalendar] = relationship(back_populates="holidays")
