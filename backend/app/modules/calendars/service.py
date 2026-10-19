# -*- coding: utf-8 -*-
"""سرویس تقویم کاری — محاسبه زمان کاری و مهلت SLA بر پایه ساعات اداری.

قواعد:
- زمان‌ها به وقت محلی تقویم (پیش‌فرض Asia/Tehran) محاسبه و در پایگاه UTC ذخیره می‌شود.
- جمعه (و روزهای غیرفعال هفته) و تعطیلات رسمی از محاسبه حذف می‌شوند.
- وقفه‌های روزانه (ناهار و ...) لحظه‌شماری نمی‌شوند.
- اگر ساعت ورودی خارج از ساعات کاری باشد، از نخستین لحظه کاری بعدی شروع می‌شود.
"""
from __future__ import annotations

import zoneinfo
from datetime import datetime, timedelta, date, time as dtime, timezone as _timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.calendars.models import WorkCalendar, CalendarHoliday, DAY_KEYS

DEFAULT_TZ = settings.TIMEZONE or "Asia/Tehran"


# ---------------- ابزارهای پایه ----------------
def _parse_hhmm(v: str | None, fallback: dtime) -> dtime:
    try:
        h, m = str(v).split(":")
        return dtime(int(h), int(m))
    except Exception:
        return fallback


def _day_key(dt: date) -> str:
    """کلید روز هفته ایرانی — شنبه اول هفته."""
    # ISO: monday=0 .. sunday=6 → ترتیب DAY_KEYS از saturday شروع می‌شود
    iso = dt.weekday()  # mon=0..sun=6
    order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    return order[iso]


def _tz(calendar: WorkCalendar):
    try:
        return zoneinfo.ZoneInfo(calendar.timezone or DEFAULT_TZ)
    except Exception:
        return zoneinfo.ZoneInfo(DEFAULT_TZ)


def _holiday_dates(calendar: WorkCalendar) -> set[tuple[int, int, int] | tuple[int, int]]:
    out = set()
    for h in calendar.holidays or []:
        if h.yearly:
            out.add((h.date.month, h.date.day))
        else:
            out.add((h.date.year, h.date.month, h.date.day))
    return out


def _is_holiday(calendar: WorkCalendar, d: date, holidays) -> bool:
    if (d.year, d.month, d.day) in holidays:
        return True
    return (d.month, d.day) in holidays


def _working_window(calendar: WorkCalendar, d: date, holidays):
    """بازه(های) کاری روز (بدون وقفه‌ها) به‌صورت فهرست (start_dt, end_dt) به وقت محلی."""
    if _is_holiday(calendar, d, holidays):
        return []
    key = _day_key(d)
    sched = (calendar.schedule_json or {}).get(key)
    if not sched or not sched.get("enabled"):
        return []
    start = datetime.combine(d, _parse_hhmm(sched.get("start"), dtime(8, 0)))
    end = datetime.combine(d, _parse_hhmm(sched.get("end"), dtime(16, 0)))
    if end <= start:
        return []
    breaks = []
    for b in (sched.get("breaks") or []):
        bs = datetime.combine(d, _parse_hhmm(b.get("start"), dtime(12, 0)))
        be = datetime.combine(d, _parse_hhmm(b.get("end"), dtime(13, 0)))
        if be > bs:
            breaks.append((bs, be))
    # شکستن بازه به قطعات کاری
    segments = [(start, end)]
    for bs, be in breaks:
        new_segments = []
        for s, e in segments:
            if be <= s or bs >= e:
                new_segments.append((s, e))
                continue
            if s < bs:
                new_segments.append((s, min(bs, e)))
            if e > be:
                new_segments.append((max(be, s), e))
        segments = [seg for seg in new_segments if seg[1] > seg[0]]
    return segments


def is_working_time(calendar: WorkCalendar, local_dt: datetime) -> bool:
    """آیا این لحظه (به وقت محلی) در ساعات کاری است؟"""
    holidays = _holiday_dates(calendar)
    for s, e in _working_window(calendar, local_dt.date(), holidays):
        if s <= local_dt < e:
            return True
    return False


def _advance(calendar: WorkCalendar, local_dt: datetime, seconds_left: float, holidays,
             max_days: int = 400) -> datetime:
    """پیشروی seconds_left ثانیه کاری از local_dt (وقت محلی)."""
    day = local_dt.date()
    cursor = local_dt
    start_local = local_dt
    for _ in range(max_days):
        for s, e in _working_window(calendar, day, holidays):
            if cursor < s:
                cursor = s
            if cursor >= e:
                continue
            available = (e - cursor).total_seconds()
            if available >= seconds_left:
                return cursor + timedelta(seconds=seconds_left)
            seconds_left -= available
            cursor = e
        # روز بعد — از ابتدای روز
        day = day + timedelta(days=1)
        cursor = datetime.combine(day, dtime(0, 0))
    # اگر در سقف روزهای بررسی چیزی یافت نشد (تقویم خالی) — بازگشت زمان تقویمی از مبدأ
    return start_local + timedelta(seconds=seconds_left)


def add_business_hours(calendar: WorkCalendar, utc_dt: datetime, hours: float) -> datetime:
    """افزودن «ساعت کاری» به زمان UTC بر پایه تقویم — خروجی UTC (naive).

    اگر تقویم هیچ روز کاری فعال نداشته باشد، زمان تقویمی (خطی) برمی‌گردد.
    """
    tz = _tz(calendar)
    if utc_dt.tzinfo is not None:
        utc_dt = utc_dt.astimezone(_timezone.utc).replace(tzinfo=None)
    local = utc_dt.replace(tzinfo=_timezone.utc).astimezone(tz).replace(tzinfo=None)
    holidays = _holiday_dates(calendar)
    result_local = _advance(calendar, local, float(hours) * 3600.0, holidays, max_days=400)
    return result_local.replace(tzinfo=tz).astimezone(_timezone.utc).replace(tzinfo=None)


def compute_due_at(db: Session, calendar_id: int | None, base_utc: datetime, hours: float) -> tuple[datetime | None, bool]:
    """مهلت انجام بر پایه تقویم؛ اگر تقویم یافت نشد (None, False) → محاسبه خطی توسط فراخواننده."""
    if not calendar_id:
        return None, False
    cal = db.get(WorkCalendar, calendar_id)
    if not cal:
        return None, False
    return add_business_hours(cal, base_utc, hours), True


def get_default_calendar(db: Session) -> WorkCalendar | None:
    return db.scalar(select(WorkCalendar).where(WorkCalendar.is_default.is_(True)))


def calendar_has_working_days(calendar: WorkCalendar) -> bool:
    sched = calendar.schedule_json or {}
    return any((sched.get(k) or {}).get("enabled") for k in DAY_KEYS)
