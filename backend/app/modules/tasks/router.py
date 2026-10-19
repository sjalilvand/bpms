# -*- coding: utf-8 -*-
"""API کارتابل: وظایف من، صف گروهی، انجام‌شده‌ها، درخواست‌های من + claim/complete."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, or_, and_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.identity.models import User, Role
from app.modules.engine.models import ProcessInstance, EngineTask, ProcessDefinition
from app.modules.engine import service as svc
from app.modules.organization.router import active_delegators
from app.modules.forms.persian import gregorian_to_jalali_str

router = APIRouter()


class CompleteIn(BaseModel):
    data: dict = {}
    result: str | None = None
    comment: str | None = None
    partial: bool = False


def _task_out(t: EngineTask, i: ProcessInstance, d: ProcessDefinition | None):
    return {
        "id": t.id, "instance_id": t.instance_id, "name": t.name, "spec_id": t.spec_id,
        "status": t.status, "assignee_id": t.assignee_id, "candidate_role": t.candidate_role,
        "claimed_by_id": t.claimed_by_id, "due_at": t.due_at.isoformat() if t.due_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "created_at_jalali": gregorian_to_jalali_str(t.created_at, with_time=True),
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "result": t.result, "comment": t.comment, "form_version_id": t.form_version_id,
        "instance": {
            "id": i.id, "title": i.title, "business_key": i.business_key, "status": i.status,
            "started_by_id": i.started_by_id,
            "process_title": d.title if d else None, "process_id": d.id if d else None,
        } if i else None,
    }


def _fetch_tasks(db: Session, where, page: int, page_size: int):
    stmt = select(EngineTask).where(where).order_by(EngineTask.id.desc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for t in rows:
        i = db.get(ProcessInstance, t.instance_id)
        d = db.get(ProcessDefinition, i.definition_id) if i else None
        items.append(_task_out(t, i, d))
    return {"items": items, "total": total}


def _accessible_assignee_ids(db: Session, user: User) -> list[int]:
    """وظایف کاربران جانشین‌شده نیز در کارتابل ظاهر می‌شود (سند §۵.۲)."""
    ids = [user.id]
    ids.extend(active_delegators(db, user.id))
    return ids


@router.get("/tasks/inbox")
def inbox(db: Session = Depends(get_db), user: User = Depends(get_current_user),
          page: int = 1, page_size: int = 20, status: str = "open", q: str = ""):
    """وظایف تخصیص‌یافته به من (و جانشین‌شده‌ها)."""
    where = EngineTask.assignee_id.in_(_accessible_assignee_ids(db, user))
    if status == "open":
        where = and_(where, EngineTask.status.in_(["ready", "claimed"]))
    elif status != "all":
        where = and_(where, EngineTask.status == status)
    if q:
        where = and_(where, EngineTask.name.contains(q))
    return _fetch_tasks(db, where, page, page_size)


@router.get("/tasks/group")
def group_queue(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                page: int = 1, page_size: int = 20, q: str = ""):
    """صف گروهی — نمایش با قواعد Claim و جلوگیری از دریافت هم‌زمان هماهنگ است."""
    my_roles = [r.code for r in user.roles]
    if not my_roles and not user.is_superadmin:
        return {"items": [], "total": 0}
    where = EngineTask.status == "ready"
    if not user.is_superadmin:
        where = and_(where, EngineTask.candidate_role.in_(my_roles), EngineTask.assignee_id.is_(None))
    else:
        where = and_(where, EngineTask.candidate_role.isnot(None), EngineTask.assignee_id.is_(None))
    if q:
        where = and_(where, EngineTask.name.contains(q))
    return _fetch_tasks(db, where, page, page_size)


@router.get("/tasks/completed")
def completed_tasks(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                    page: int = 1, page_size: int = 20):
    where = and_(EngineTask.status == "completed",
                 or_(EngineTask.completed_by_id == user.id, EngineTask.claimed_by_id == user.id))
    return _fetch_tasks(db, where, page, page_size)


@router.get("/tasks/{tid}")
def get_task(tid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.get(EngineTask, tid)
    if not t:
        raise HTTPException(404, "وظیفه یافت نشد")
    i = db.get(ProcessInstance, t.instance_id)
    d = db.get(ProcessDefinition, i.definition_id) if i else None
    # کنترل دسترسی مشاهده: تخصیص‌یافته، گروه نامزد، یا ناظر/مدیر
    my_roles = [r.code for r in user.roles]
    allowed = (user.is_superadmin or t.assignee_id in _accessible_assignee_ids(db, user)
               or (t.candidate_role in my_roles if t.candidate_role else False)
               or i.started_by_id == user.id)
    from app.core.deps import has_permission
    if not allowed and not (has_permission(user, "monitor.view")):
        raise HTTPException(403, "دسترسی به این وظیفه ندارید")
    return _task_out(t, i, d)


@router.get("/tasks/{tid}/data")
def get_task_data(tid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """داده فعلی موتور برای این وظیفه (نمایش داده‌های مراحل قبلی در فرم)."""
    t = db.get(EngineTask, tid)
    if not t:
        raise HTTPException(404, "وظیفه یافت نشد")
    i = db.get(ProcessInstance, t.instance_id)
    try:
        wf = svc.load_workflow(i)
        from app.modules.engine import adapter
        et = adapter.get_user_task(wf, t.task_uuid)
        data = dict(et.data or {}) if et else {}
    except Exception:
        data = {}
    # پوشاندن متغیرهای داخلی
    out = {k: v for k, v in data.items() if not k.startswith("_")}
    return {"data": out}


@router.post("/tasks/{tid}/claim")
def claim(tid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.get(EngineTask, tid)
    if not t:
        raise HTTPException(404, "وظیفه یافت نشد")
    try:
        svc.claim_task(db, t, user)
    except ValueError as e:
        raise HTTPException(409, e.args[0])
    return {"ok": True, "status": t.status}


@router.post("/tasks/{tid}/release")
def release(tid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.get(EngineTask, tid)
    if not t:
        raise HTTPException(404, "وظیفه یافت نشد")
    try:
        svc.release_task(db, t, user)
    except ValueError as e:
        raise HTTPException(400, e.args[0])
    return {"ok": True, "status": t.status}


@router.post("/tasks/{tid}/complete")
def complete(tid: int, body: CompleteIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """تکمیل وظیفه — اعتبارسنجی فرم در سرور و جلوگیری از تکمیل تکراری (AC-12)."""
    t = db.get(EngineTask, tid)
    if not t:
        raise HTTPException(404, "وظیفه یافت نشد")
    try:
        svc.complete_task(db, t, user, data=body.data, result=body.result,
                          comment=body.comment, partial=body.partial)
    except ValueError as e:
        payload = e.args[0]
        if isinstance(payload, dict):
            raise HTTPException(400, payload)
        raise HTTPException(409, payload)
    return {"ok": True, "status": t.status}
