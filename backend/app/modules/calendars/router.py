# -*- coding: utf-8 -*-
"""API تقویم کاری — تقویم‌ها، برنامه هفتگی، تعطیلات و پیش‌نمایش مهلت کاری."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, model_validator
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_perm
from app.modules.identity.models import User
from app.modules.calendars.models import WorkCalendar, CalendarHoliday, DAY_KEYS
from app.modules.calendars import service as csvc
from app.modules.forms.persian import gregorian_to_jalali_str
from app.modules.audit.service import log_action

router = APIRouter()


class DayRule(BaseModel):
    enabled: bool = False
    start: str = "08:00"
    end: str = "16:00"
    breaks: list[dict] = []


class CalendarIn(BaseModel):
    name: str
    description: str = ""
    timezone: str = "Asia/Tehran"
    schedule_json: dict[str, DayRule] = {}
    is_default: bool = False


class HolidayIn(BaseModel):
    date: date
    title: str = ""
    yearly: bool = False


class PreviewIn(BaseModel):
    from_datetime: datetime | None = None   # UTC ISO؛ پیش‌فرض اکنون
    hours: float


def _schedule_out(cal: WorkCalendar) -> dict:
    sched = cal.schedule_json or {}
    out = {}
    for k in DAY_KEYS:
        rule = sched.get(k) or {}
        out[k] = {
            "enabled": bool(rule.get("enabled")),
            "start": rule.get("start") or "08:00",
            "end": rule.get("end") or "16:00",
            "breaks": rule.get("breaks") or [],
        }
    return out


def calendar_out(c: WorkCalendar, with_holidays: bool = False) -> dict:
    out = {
        "id": c.id, "name": c.name, "description": c.description,
        "timezone": c.timezone, "is_default": c.is_default,
        "schedule_json": _schedule_out(c),
        "has_working_days": csvc.calendar_has_working_days(c),
        "holiday_count": len(c.holidays or []),
    }
    if with_holidays:
        out["holidays"] = [{
            "id": h.id, "date": h.date.isoformat(),
            "date_jalali": gregorian_to_jalali_str(h.date),
            "title": h.title, "yearly": h.yearly,
        } for h in (c.holidays or [])]
    return out


@router.get("/calendars")
def list_calendars(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(WorkCalendar).order_by(WorkCalendar.id)).all()
    return {"items": [calendar_out(c) for c in rows]}


@router.post("/calendars")
def create_calendar(body: CalendarIn, db: Session = Depends(get_db), user: User = Depends(require_perm("calendar.manage")), request: Request = None):
    c = WorkCalendar(name=body.name, description=body.description, timezone=body.timezone,
                     schedule_json={k: v.model_dump() for k, v in body.schedule_json.items()},
                     is_default=body.is_default, created_by_id=user.id)
    if body.is_default:
        for other in db.scalars(select(WorkCalendar).where(WorkCalendar.is_default.is_(True))).all():
            other.is_default = False
    db.add(c)
    db.commit()
    log_action(db, user.id, "calendar.created", "calendar", c.id, {"name": c.name}, request)
    return {"id": c.id}


@router.get("/calendars/{cid}")
def get_calendar(cid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(WorkCalendar, cid)
    if not c:
        raise HTTPException(404, "تقویم یافت نشد")
    return calendar_out(c, with_holidays=True)


@router.put("/calendars/{cid}")
def update_calendar(cid: int, body: CalendarIn, db: Session = Depends(get_db), user: User = Depends(require_perm("calendar.manage")), request: Request = None):
    c = db.get(WorkCalendar, cid)
    if not c:
        raise HTTPException(404, "تقویم یافت نشد")
    c.name, c.description, c.timezone = body.name, body.description, body.timezone
    c.schedule_json = {k: v.model_dump() for k, v in body.schedule_json.items()}
    if body.is_default and not c.is_default:
        for other in db.scalars(select(WorkCalendar).where(WorkCalendar.is_default.is_(True))).all():
            other.is_default = False
        c.is_default = True
    db.commit()
    log_action(db, user.id, "calendar.updated", "calendar", c.id, {}, request)
    return {"ok": True}


@router.delete("/calendars/{cid}")
def delete_calendar(cid: int, db: Session = Depends(get_db), user: User = Depends(require_perm("calendar.manage")), request: Request = None):
    c = db.get(WorkCalendar, cid)
    if not c:
        raise HTTPException(404, "تقویم یافت نشد")
    db.delete(c)
    db.commit()
    log_action(db, user.id, "calendar.deleted", "calendar", cid, {}, request)
    return {"ok": True}


@router.post("/calendars/{cid}/holidays")
def add_holiday(cid: int, body: HolidayIn, db: Session = Depends(get_db), user: User = Depends(require_perm("calendar.manage")), request: Request = None):
    c = db.get(WorkCalendar, cid)
    if not c:
        raise HTTPException(404, "تقویم یافت نشد")
    exists = db.scalar(select(CalendarHoliday).where(
        CalendarHoliday.calendar_id == cid, CalendarHoliday.date == body.date))
    if exists:
        raise HTTPException(400, "این تاریخ قبلاً در تعطیلات ثبت شده است")
    h = CalendarHoliday(calendar_id=cid, date=body.date, title=body.title, yearly=body.yearly)
    db.add(h)
    db.commit()
    log_action(db, user.id, "calendar.holiday_added", "calendar", cid, {"date": body.date.isoformat()}, request)
    return {"id": h.id, "date_jalali": gregorian_to_jalali_str(h.date)}


@router.delete("/calendars/{cid}/holidays/{hid}")
def delete_holiday(cid: int, hid: int, db: Session = Depends(get_db), user: User = Depends(require_perm("calendar.manage")), request: Request = None):
    h = db.get(CalendarHoliday, hid)
    if not h or h.calendar_id != cid:
        raise HTTPException(404, "تعطیلی یافت نشد")
    db.delete(h)
    db.commit()
    log_action(db, user.id, "calendar.holiday_removed", "calendar", cid, {}, request)
    return {"ok": True}


@router.post("/calendars/{cid}/preview")
def preview(cid: int, body: PreviewIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """پیش‌نمایش محاسبه مهلت: از زمان مبدا + ساعت کاری → زمان تحویل."""
    c = db.get(WorkCalendar, cid)
    if not c:
        raise HTTPException(404, "تقویم یافت نشد")
    base = body.from_datetime or datetime.utcnow()
    if not csvc.calendar_has_working_days(c):
        raise HTTPException(400, "این تقویم روز کاری فعالی ندارد؛ ابتدا برنامه هفتگی را تنظیم کنید")
    due = csvc.add_business_hours(c, base.replace(tzinfo=None) if base.tzinfo else base, body.hours)
    # محاسبه ساده نمایشی: زمان کاری مصرف‌شده در بازه
    return {
        "from": base.replace(microsecond=0).isoformat(),
        "due_at": due.replace(microsecond=0).isoformat(),
        "due_at_jalali": gregorian_to_jalali_str(due, with_time=True),
        "calendar_hours": body.hours,
    }


@router.get("/calendars/default/summary")
def default_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """خلاصه تقویم پیش‌فرض برای نمایش در داشبورد."""
    c = csvc.get_default_calendar(db)
    if not c:
        return {"exists": False}
    return {"exists": True, "id": c.id, "name": c.name, "schedule": _schedule_out(c)}
