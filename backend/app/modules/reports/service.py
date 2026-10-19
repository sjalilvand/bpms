# -*- coding: utf-8 -*-
"""فاز ۶ — موتور محاسبه KPI و گزارش‌ساز.

منبع داده: ProcessInstance (زمان چرخه)، EngineTask (زمان انتظار/رسیدگی، SLA)
و ProcessDefinition (گروه‌بندی بر فرایند). همه محاسبات روی بازه زمانی قابل
فیلتر (days یا date_from/date_to) و تعریف فرایند مشخص انجام می‌شود.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.engine.models import EngineTask, InstanceEvent, ProcessDefinition, ProcessInstance
from app.modules.identity.models import User


# ---------- ابزارهای داخلی ----------

def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is None else dt.astimezone(timezone.utc).replace(tzinfo=None)


def _resolve_period(days: int | None, date_from: str | None, date_to: str | None) -> tuple[datetime, datetime | None]:
    """بازه [از، تا) — پیش‌فرض: days روز اخیر. date_to انضمامی تا آخر روز."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if date_from:
        frm = _as_utc(datetime.fromisoformat(date_from.replace("Z", "+00:00")))
    else:
        frm = now - timedelta(days=max(1, int(days or 30)))
    if date_to:
        to = _as_utc(datetime.fromisoformat(date_to.replace("Z", "+00:00"))) + timedelta(days=1) - timedelta(seconds=1)
    else:
        to = None
    return frm, to


def _instance_filters(stmt, frm: datetime, to: datetime | None, definition_id: int | None, status: str | None):
    stmt = stmt.where(ProcessInstance.started_at >= frm)
    if to:
        stmt = stmt.where(ProcessInstance.started_at <= to)
    if definition_id:
        stmt = stmt.where(ProcessInstance.definition_id == definition_id)
    if status:
        stmt = stmt.where(ProcessInstance.status == status)
    return stmt


def _pctl(sorted_vals: list[float], p: int) -> float:
    """صدک ساده — برای مقیاس عملیاتی کافی است."""
    if not sorted_vals:
        return 0.0
    import math
    idx = max(0, min(len(sorted_vals) - 1, math.ceil(p / 100 * len(sorted_vals)) - 1))
    return sorted_vals[idx]


def _seconds(delta: timedelta | None) -> float | None:
    return None if delta is None else max(0.0, delta.total_seconds())


def _avg(vals: list[float]) -> float:
    return round(sum(vals) / len(vals), 1) if vals else 0.0


def _round1(v: float | None) -> float | None:
    return None if v is None else round(v, 1)


# ---------- شاخص‌های کلی (Overview) ----------

def kpi_overview(db: Session, days: int = 30, date_from: str | None = None,
                 date_to: str | None = None, definition_id: int | None = None,
                 status: str | None = None) -> dict:
    frm, to = _resolve_period(days, date_from, date_to)
    base = _instance_filters(select(ProcessInstance), frm, to, definition_id, status)
    instances = db.scalars(base).all()

    by_status: dict[str, int] = {"running": 0, "completed": 0, "cancelled": 0, "error": 0}
    cycle_seconds: list[float] = []
    for it in instances:
        by_status[it.status] = by_status.get(it.status, 0) + 1
        if it.finished_at and it.status == "completed":
            c = _seconds(_as_utc(it.finished_at) - _as_utc(it.started_at))
            if c is not None:
                cycle_seconds.append(c)

    total = len(instances)
    completed = by_status.get("completed", 0)
    cycle_sorted = sorted(cycle_seconds)

    # وظایف بازه (از طریق نمونه‌های بازه)
    inst_ids = [it.id for it in instances]
    tasks: list[EngineTask] = []
    if inst_ids:
        tasks = db.scalars(select(EngineTask).where(EngineTask.instance_id.in_(inst_ids))).all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    wait_seconds, handle_seconds = [], []
    t_ready = t_claimed = t_completed = t_overdue = t_escalated = t_warned = 0
    for t in tasks:
        if t.status == "ready":
            t_ready += 1
        elif t.status == "claimed":
            t_claimed += 1
        elif t.status == "completed":
            t_completed += 1
        if t.due_at and t.status in ("ready", "claimed") and _as_utc(t.due_at) < now:
            t_overdue += 1
        if t.sla_warned_at:
            t_warned += 1
        if t.sla_escalated_at:
            t_escalated += 1
        created = _as_utc(t.created_at) if t.created_at else None
        claimed = _as_utc(t.claimed_at) if t.claimed_at else None
        done = _as_utc(t.completed_at) if t.completed_at else None
        if claimed and created:
            w = _seconds(claimed - created)
            if w is not None:
                wait_seconds.append(w)
        if done and created:
            h = _seconds(done - claimed) if (claimed and claimed > created) else _seconds(done - created)
            if h is not None:
                handle_seconds.append(h)

    return {
        "period": {"from": frm.isoformat(), "to": (to or now).isoformat()},
        "filters": {"definition_id": definition_id, "status": status, "days": days},
        "instances": {
            "total": total,
            "by_status": by_status,
            "completion_rate": round(completed * 100.0 / total, 1) if total else 0.0,
            "avg_per_day": round(total / max(1, (min(to or now, now) - frm).days + 1), 2),
        },
        "cycle_time_seconds": {
            "avg": _avg(cycle_sorted),
            "min": _round1(cycle_sorted[0]) if cycle_sorted else 0.0,
            "max": _round1(cycle_sorted[-1]) if cycle_sorted else 0.0,
            "p50": _round1(_pctl(cycle_sorted, 50)),
            "p95": _round1(_pctl(cycle_sorted, 95)),
            "completed_count": len(cycle_sorted),
        },
        "tasks": {
            "total": len(tasks),
            "ready": t_ready,
            "claimed": t_claimed,
            "completed": t_completed,
            "overdue_active": t_overdue,
            "avg_wait_seconds": _avg(wait_seconds),
            "avg_handling_seconds": _avg(handle_seconds),
        },
        "sla": {
            "warned": t_warned,
            "escalated": t_escalated,
            "breach_rate": round(t_escalated * 100.0 / len(tasks), 1) if tasks else 0.0,
        },
    }


# ---------- گلوگاه‌ها (Bottlenecks) ----------

def kpi_bottlenecks(db: Session, days: int = 30, date_from: str | None = None,
                    date_to: str | None = None, definition_id: int | None = None) -> list[dict]:
    frm, to = _resolve_period(days, date_from, date_to)
    inst_stmt = _instance_filters(select(ProcessInstance), frm, to, definition_id, None)
    inst_ids = [it.id for it in db.scalars(inst_stmt).all()]
    if not inst_ids:
        return []

    tasks = db.scalars(select(EngineTask).where(
        EngineTask.instance_id.in_(inst_ids), EngineTask.created_at >= frm)).all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    groups: dict[tuple[str, str], list[EngineTask]] = {}
    for t in tasks:
        groups.setdefault((t.spec_id, t.name or t.spec_id), []).append(t)

    rows: list[dict] = []
    for (spec_id, name), items in groups.items():
        created = len(items)
        completed_items = [t for t in items if t.status == "completed"]
        wait, handle = [], []
        overdue = escalated = 0
        for t in items:
            c = _as_utc(t.created_at) if t.created_at else None
            cl = _as_utc(t.claimed_at) if t.claimed_at else None
            d = _as_utc(t.completed_at) if t.completed_at else None
            if cl and c:
                w = _seconds(cl - c)
                if w is not None:
                    wait.append(w)
            if d and c:
                h = _seconds(d - cl) if (cl and cl > c) else _seconds(d - c)
                if h is not None:
                    handle.append(h)
            if t.due_at and t.status in ("ready", "claimed") and _as_utc(t.due_at) < now:
                overdue += 1
            if t.sla_escalated_at:
                escalated += 1
        handle_sorted = sorted(handle)
        rows.append({
            "spec_id": spec_id,
            "name": name,
            "created": created,
            "completed": len(completed_items),
            "pending": created - len(completed_items),
            "avg_wait_seconds": _avg(wait),
            "avg_handling_seconds": _avg(handle_sorted),
            "max_handling_seconds": _round1(handle_sorted[-1]) if handle_sorted else 0.0,
            "p95_handling_seconds": _round1(_pctl(handle_sorted, 95)),
            "overdue_active": overdue,
            "sla_escalated": escalated,
        })
    rows.sort(key=lambda r: (r["avg_handling_seconds"], r["avg_wait_seconds"]), reverse=True)
    return rows


# ---------- بار کاری افراد (Workload) ----------

def kpi_workload(db: Session, days: int = 30, date_from: str | None = None,
                 date_to: str | None = None, definition_id: int | None = None) -> list[dict]:
    frm, to = _resolve_period(days, date_from, date_to)
    inst_stmt = _instance_filters(select(ProcessInstance), frm, to, definition_id, None)
    inst_ids = [it.id for it in db.scalars(inst_stmt).all()]
    if not inst_ids:
        return []

    tasks = db.scalars(select(EngineTask).where(
        EngineTask.instance_id.in_(inst_ids))).all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    by_user: dict[int | None, dict[str, Any]] = {}
    for t in tasks:
        uid = t.completed_by_id or t.assignee_id or t.claimed_by_id
        if uid is None and t.candidate_role:
            key = ("role", t.candidate_role)
        else:
            key = ("user", uid)
        g = by_user.setdefault(key, {
            "kind": key[0], "ref": key[1], "name": None,
            "completed": 0, "active": 0, "overdue": 0, "escalated": 0,
            "handle_seconds": [],
        })
        c = _as_utc(t.created_at) if t.created_at else None
        d = _as_utc(t.completed_at) if t.completed_at else None
        if t.status == "completed":
            g["completed"] += 1
            if d and c:
                h = _seconds(d - (_as_utc(t.claimed_at) if t.claimed_at else c))
                if h is not None:
                    g["handle_seconds"].append(h)
        elif t.status in ("ready", "claimed"):
            g["active"] += 1
            if t.due_at and _as_utc(t.due_at) < now:
                g["overdue"] += 1
        if t.sla_escalated_at:
            g["escalated"] += 1

    # نام کاربران/نقش‌ها
    user_ids = [k[1] for k in by_user if k[0] == "user" and k[1]]
    names: dict[int, str] = {}
    if user_ids:
        for u in db.scalars(select(User).where(User.id.in_(user_ids))).all():
            names[u.id] = u.full_name

    rows: list[dict] = []
    for g in by_user.values():
        hs = sorted(g["handle_seconds"])
        rows.append({
            "kind": g["kind"],
            "ref": g["ref"],
            "name": names.get(g["ref"]) if g["kind"] == "user" else None,
            "label": (names.get(g["ref"]) or f"کاربر #{g['ref']}") if g["kind"] == "user"
                     else f"نقش «{g['ref']}» (صف گروهی)",
            "completed": g["completed"],
            "active": g["active"],
            "overdue_active": g["overdue"],
            "sla_escalated": g["escalated"],
            "avg_handling_seconds": _avg(hs),
        })
    rows.sort(key=lambda r: (r["completed"], r["active"]), reverse=True)
    return rows


# ---------- حجم روزانه (Volume) ----------

def kpi_volume(db: Session, days: int = 30, date_from: str | None = None,
               date_to: str | None = None, definition_id: int | None = None) -> list[dict]:
    frm, to = _resolve_period(days, date_from, date_to)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    end = min(to, now) if to else now

    started = db.scalars(_instance_filters(
        select(ProcessInstance), frm, None, definition_id, None)).all()
    completed_stmt = _instance_filters(select(ProcessInstance), frm, None, definition_id, "completed")
    completed_rows = db.scalars(completed_stmt).all()

    days_list: list[dict] = []
    cur = frm.date()
    end_date = end.date()
    while cur <= end_date:
        days_list.append({"date": cur.isoformat(), "started": 0, "completed": 0})
        cur += timedelta(days=1)
    idx = {d["date"]: d for d in days_list}

    for it in started:
        k = _as_utc(it.started_at).date().isoformat()
        if k in idx:
            idx[k]["started"] += 1
    for it in completed_rows:
        if it.finished_at:
            k = _as_utc(it.finished_at).date().isoformat()
            if k in idx:
                idx[k]["completed"] += 1
    return days_list


# ---------- فهرست فرایندها برای فیلتر ----------

def process_options(db: Session) -> list[dict]:
    rows = db.execute(
        select(ProcessDefinition.id, ProcessDefinition.key, ProcessDefinition.title)
        .order_by(ProcessDefinition.title)).all()
    return [{"id": r[0], "key": r[1], "title": r[2]} for r in rows]


# ---------- اجرای گزارش ذخیره‌شده ----------

DATASETS = {
    "overview": kpi_overview,
    "bottlenecks": kpi_bottlenecks,
    "workload": kpi_workload,
    "volume": kpi_volume,
}


def run_saved(db: Session, dataset: str, filters: dict) -> dict:
    """اجرای گزارش ذخیره‌شده با نرمال‌سازی خروجی (سازگار با API شاخص‌ها)."""
    fn = DATASETS.get(dataset)
    if not fn:
        raise ValueError(f"مجموعه‌داده «{dataset}» شناخته‌شده نیست")
    kwargs = {
        "days": int(filters.get("days") or 30),
        "date_from": filters.get("date_from") or None,
        "date_to": filters.get("date_to") or None,
        "definition_id": filters.get("definition_id") or None,
    }
    if dataset == "overview":
        kwargs["status"] = filters.get("status") or None
        return fn(db, **kwargs)
    return {"items": fn(db, **kwargs)}
