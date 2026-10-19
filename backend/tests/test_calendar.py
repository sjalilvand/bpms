# -*- coding: utf-8 -*-
"""تست تقویم کاری (فاز ۳) — ساعات اداری، وقفه، تعطیلات و مهلت کاری.

تقویم پیش‌فرض: شنبه تا چهارشنبه ۸–۱۶ (وقفه ۱۲–۱۳)، پنجشنبه ۸–۱۲، جمعه تعطیل.
تاریخ‌ها naive-UTC در پایگاه ذخیره می‌شوند؛ اینجا برای سادگی مقایسه با UTC انجام می‌شود.
"""
from datetime import datetime, date

import pytest

from app.modules.calendars.models import WorkCalendar, CalendarHoliday
from app.modules.calendars.service import (
    add_business_hours, is_working_time, calendar_has_working_days, _holiday_dates,
)
from app.modules.decisions.engine import DecisionError  # noqa: F401 (تضمین ایمپورت ماژول‌ها)


def _calendar(schedule: dict | None = None, holidays: list[tuple] | None = None) -> WorkCalendar:
    cal = WorkCalendar(name="تقویم آزمون", timezone="Asia/Tehran", schedule_json=schedule or {})
    cal.holidays = []
    return cal


def _std_schedule() -> dict:
    return {
        "saturday":  {"enabled": True, "start": "08:00", "end": "16:00", "breaks": [{"start": "12:00", "end": "13:00"}]},
        "sunday":    {"enabled": True, "start": "08:00", "end": "16:00", "breaks": [{"start": "12:00", "end": "13:00"}]},
        "monday":    {"enabled": True, "start": "08:00", "end": "16:00", "breaks": [{"start": "12:00", "end": "13:00"}]},
        "tuesday":   {"enabled": True, "start": "08:00", "end": "16:00", "breaks": [{"start": "12:00", "end": "13:00"}]},
        "wednesday": {"enabled": True, "start": "08:00", "end": "16:00", "breaks": [{"start": "12:00", "end": "13:00"}]},
        "thursday":  {"enabled": True, "start": "08:00", "end": "12:00", "breaks": []},
        "friday":    {"enabled": False, "start": "08:00", "end": "16:00", "breaks": []},
    }


# 2026-10-22 = پنجشنبه، 2026-10-23 = جمعه، 2026-10-24 = شنبه، 2026-10-25 = یکشنبه
THU = datetime(2026, 10, 22)
FRI = datetime(2026, 10, 23)
SAT = datetime(2026, 10, 24)
SUN = datetime(2026, 10, 25)


def _local(utc: datetime, hours: int = 3, minutes: int = 30):
    """نمایش محلی Tehran از UTC ذخیره‌شده."""
    return utc


class TestWorkingTime:
    # ورودی is_working_time بر اساس قرارداد API «وقت محلی تقویم» است
    def test_inside_working_hours(self):
        cal = _calendar(_std_schedule())
        assert is_working_time(cal, SAT.replace(hour=10, minute=0)) is True  # ۱۰:۰۰ تهران

    def test_break_time_not_working(self):
        cal = _calendar(_std_schedule())
        assert is_working_time(cal, SAT.replace(hour=12, minute=30)) is False  # وقفه ناهار

    def test_friday_not_working(self):
        cal = _calendar(_std_schedule())
        assert is_working_time(cal, FRI.replace(hour=10, minute=0)) is False

    def test_before_and_after_hours(self):
        cal = _calendar(_std_schedule())
        assert is_working_time(cal, SAT.replace(hour=7, minute=30)) is False
        assert is_working_time(cal, SAT.replace(hour=17, minute=30)) is False

    def test_holiday_not_working(self):
        cal = _calendar(_std_schedule())
        cal.holidays = [CalendarHoliday(calendar_id=1, date=date(2026, 10, 24), title="تعطیل", yearly=False)]
        assert is_working_time(cal, SAT.replace(hour=10, minute=0)) is False

    def test_yearly_holiday(self):
        cal = _calendar(_std_schedule())
        cal.holidays = [CalendarHoliday(calendar_id=1, date=date(2020, 10, 24), title="سالانه", yearly=True)]
        assert is_working_time(cal, SAT.replace(hour=10, minute=0)) is False
        # سال دیگر همان روز/ماه
        assert is_working_time(cal, datetime(2027, 10, 24, 10, 0)) is False


class TestBusinessHours:
    # ورودی add_business_hours بر اساس قرارداد API «UTC» است؛ تهران = UTC+۳:۳۰
    def test_simple_same_day(self):
        cal = _calendar(_std_schedule())
        # شنبه 8:00 UTC = 11:30 تهران + 0.5 ساعت کاری = 12:00 تهران (قبل از وقفه) = 8:30 UTC
        due = add_business_hours(cal, SAT.replace(hour=8, minute=0), 0.5)
        assert due == SAT.replace(hour=8, minute=30)

    def test_spans_lunch_break(self):
        cal = _calendar(_std_schedule())
        # شنبه 8:00 UTC = 11:30 تهران + 1 ساعت: ۳۰ دقیقه تا وقفه + ۳۰ دقیقه بعد وقفه = ۱۳:۳۰ تهران = 10:00 UTC
        due = add_business_hours(cal, SAT.replace(hour=8, minute=0), 1)
        assert due == SAT.replace(hour=10, minute=0)

    def test_spans_to_next_day(self):
        cal = _calendar(_std_schedule())
        # شنبه 8:00 UTC = 11:30 تهران + 4 ساعت: ۳۰ دقیقه (تا ۱۲) + ۳ ساعت (۱۳ تا ۱۶) = ۳.۵ ساعت؛
        # ۰.۵ ساعت باقی → یکشنبه 8:30 تهران = 5:00 UTC
        due = add_business_hours(cal, SAT.replace(hour=8, minute=0), 4)
        assert due == SUN.replace(hour=5, minute=0)

    def test_skips_friday(self):
        cal = _calendar(_std_schedule())
        # پنجشنبه 8:00 UTC = 11:30 تهران + 1 ساعت: ۳۰ دقیقه تا ۱۲ (پایان روز پنجشنبه) +
        # جمعه تعطیل → شنبه 8:30 تهران = 5:00 UTC
        due = add_business_hours(cal, THU.replace(hour=8, minute=0), 1)
        assert due == SAT.replace(hour=5, minute=0)
        # +2 ساعت → شنبه 9:30 تهران = 6:00 UTC
        due2 = add_business_hours(cal, THU.replace(hour=8, minute=0), 2)
        assert due2 == SAT.replace(hour=6, minute=0)

    def test_start_outside_hours_moves_to_next_start(self):
        cal = _calendar(_std_schedule())
        # شنبه 8:30 UTC = 12:00 تهران — ابتدای وقفه → ادامه از ۱۳:۰۰ + ۰.۵ ساعت = ۱۳:۳۰ تهران = 10:00 UTC
        due = add_business_hours(cal, SAT.replace(hour=8, minute=30), 0.5)
        assert due == SAT.replace(hour=10, minute=0)
        # جمعه 6:00 UTC = 9:30 تهران (تعطیل) → شنبه 8:00 + ۰.۵ ساعت = 8:30 تهران = 5:00 UTC
        due2 = add_business_hours(cal, FRI.replace(hour=6, minute=0), 0.5)
        assert due2 == SAT.replace(hour=5, minute=0)

    def test_empty_calendar_falls_back_to_linear(self):
        cal = _calendar({})  # هیچ روز کاری
        base = SAT.replace(hour=8, minute=0)
        due = add_business_hours(cal, base, 3)
        assert due == base.replace(hour=11, minute=0)
        assert calendar_has_working_days(cal) is False

    def test_holiday_extends_due(self):
        cal = _calendar(_std_schedule())
        cal.holidays = [CalendarHoliday(calendar_id=1, date=date(2026, 10, 24), title="شنبه تعطیل", yearly=False)]
        # پنجشنبه 11:30 تهران + 2 ساعت: ۳۰ دقیقه تا پایان روز پنجشنبه + شنبه تعطیل → یکشنبه 9:30 تهران = 6:00 UTC
        due = add_business_hours(cal, THU.replace(hour=8, minute=0), 2)
        assert due == SUN.replace(hour=6, minute=0)
