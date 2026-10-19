# -*- coding: utf-8 -*-
"""بررسی SLA وظایف — هشدار پیش از مهلت و فرازدگی مهلت (اجرا توسط Worker).

قواعد:
- هشدار: وقتی ≥ BPMS_SLA_WARN_PCT (پیش‌فرض ۸۰٪) از زمان مجاز سپری شده باشد.
- فرازدگی: وقتی due_at گذشته باشد.
- هر حالت فقط یک‌بار برای هر وظیفه اعلام می‌شود (sla_warned_at / sla_escalated_at).
- برای وظایف بدون due_at، اگر SLA ساعت در اتصال تعریف شده باشد محاسبه تقویمی انجام می‌شود
  (این کار هنگام ایجاد وظیفه در _sync_tasks انجام شده است).
"""
from __future__ import annotations

import os
from datetime import timedelta

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.engine.models import EngineTask, ProcessInstance
from app.modules.identity.models import User
from app.modules.notifications.service import notify_user, notify_role
from app.modules.events.listeners import queue_event


def sla_check(db: Session | None = None, warn_pct: float | None = None) -> dict:
    """اسکن وظایف باز برای هشدار/فرازدگی SLA — idempotent."""
    own = db is None
    if own:
        db = SessionLocal()
    try:
        pct = warn_pct if warn_pct is not None else float(os.environ.get("BPMS_SLA_WARN_PCT", "80") or 80)
        now_rows = _utcnow()
        warned, escalated = 0, 0
        open_tasks = db.scalars(select(EngineTask).where(EngineTask.status.in_(["ready", "claimed"]))).all()
        for t in open_tasks:
            if not t.due_at:
                continue
            remaining = t.due_at - now_rows
            total_hint = _estimate_total(t)
            # هشدار پیش از مهلت
            if t.sla_warned_at is None and remaining.total_seconds() > 0:
                threshold = _warn_threshold(total_hint, remaining, pct)
                if threshold:
                    _notify(db, t, "هشدار مهلت وظیفه",
                            f"«{t.name}» به‌زودی از مهلت تعیین‌شده خارج می‌شود", "warn")
                    t.sla_warned_at = now_rows
                    warned += 1
            # فرازدگی مهلت
            if t.sla_escalated_at is None and remaining.total_seconds() <= 0:
                _notify(db, t, "فرازدگی مهلت وظیفه",
                        f"«{t.name}» از مهلت تعیین‌شده گذشته است", "overdue")
                t.sla_escalated_at = now_rows
                escalated += 1
        db.commit()
        return {"warned": warned, "escalated": escalated, "checked": len(open_tasks)}
    finally:
        if own:
            db.close()


def _warn_threshold(total_hint: timedelta | None, remaining: timedelta, pct: float) -> bool:
    """آیا از آستانه هشدار عبور کرده‌ایم؟ اگر کل زمان معلوم نبود، ۲ ساعت آخر را هشدار می‌دهیم."""
    if total_hint and total_hint.total_seconds() > 0:
        return remaining <= total_hint * (1 - pct / 100.0)
    return remaining <= timedelta(hours=2)


def _estimate_total(task: EngineTask) -> timedelta | None:
    """برآورد کل زمان مجاز: از ایجاد وظیفه تا due_at."""
    if task.created_at and task.due_at:
        return task.due_at - task.created_at
    return None


def _notify(db: Session, task: EngineTask, title: str, body: str, kind: str) -> None:
    payload = {"task_id": task.id, "instance_id": task.instance_id,
               "task": task.name, "kind": kind, "due_at": task.due_at.isoformat() if task.due_at else None}
    notified_users: set[int] = set()
    if task.claimed_by_id:
        notify_user(db, task.claimed_by_id, title, body, link=f"/inbox?task={task.id}")
        notified_users.add(task.claimed_by_id)
    elif task.assignee_id:
        notify_user(db, task.assignee_id, title, body, link=f"/inbox?task={task.id}")
        notified_users.add(task.assignee_id)
    elif task.candidate_role:
        notify_role(db, task.candidate_role, title, body, link=f"/inbox?task={task.id}")
    # رویداد زنده برای به‌روزرسانی داشبورد/کارتابل
    instance = db.get(ProcessInstance, task.instance_id)
    watchers = set(notified_users)
    if instance and instance.started_by_id:
        watchers.add(instance.started_by_id)
    queue_event(db, list(watchers), "sla", payload)


def _utcnow():
    from app.modules.engine.service import now
    return now()
