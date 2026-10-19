# -*- coding: utf-8 -*-
"""API نمونه‌های اجرایی: شروع، فهرست، جزئیات، وضعیت زنده، لغو، tick تایمر."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_perm
from app.modules.identity.models import User
from app.modules.engine import adapter
from app.modules.engine import service as svc
from app.modules.engine.models import ProcessDefinition, ProcessVersion, ProcessInstance, EngineTask, InstanceEvent, Incident
from app.modules.forms.persian import gregorian_to_jalali_str
from app.modules.audit.service import log_action

router = APIRouter()


class StartIn(BaseModel):
    version_id: int | None = None          # پیش‌فرض: آخرین نسخه منتشرشده
    definition_id: int | None = None
    data: dict = {}
    business_key: str | None = None
    title: str | None = None


def _jalalize(d: dict) -> dict:
    """نمایش جلالی برای فیلدهای متداول تاریخ."""
    for k in list(d.keys()):
        if isinstance(d[k], str) and len(d[k]) == 10 and d[k][4] == "-" and d[k][:2] in ("13", "14", "15", "20"):
            d[k + "_jalali"] = gregorian_to_jalali_str(d[k])
    return d


@router.post("/process-instances")
def start_instance(body: StartIn, db: Session = Depends(get_db), user: User = Depends(get_current_user), request: Request = None):
    if not user.is_superadmin:
        # شروع فرایند مجوز صریح می‌خواهد
        from app.core.deps import has_permission
        if not has_permission(user, "process.start"):
            raise HTTPException(403, "دسترسی شروع فرایند ندارید")
    if body.version_id:
        v = db.get(ProcessVersion, body.version_id)
    elif body.definition_id:
        d = db.get(ProcessDefinition, body.definition_id)
        if not d:
            raise HTTPException(404, "فرایند یافت نشد")
        v = d.latest_published
    else:
        raise HTTPException(400, "فرایند یا نسخه مشخص نشده است")
    if not v or v.status != "published":
        raise HTTPException(400, "نسخه منتشرشده‌ای برای شروع وجود ندارد")
    try:
        inst = svc.start_instance(db, v, user, data=body.data or {},
                                  business_key=body.business_key, title=body.title)
    except ValueError as e:
        raise HTTPException(400, e.args[0])
    except adapter.EngineParseError as e:
        raise HTTPException(400, str(e))
    return {"id": inst.id, "title": inst.title, "status": inst.status}


@router.get("/process-instances")
def list_instances(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                   page: int = 1, page_size: int = 20, status: str = "", q: str = "",
                   definition_id: int | None = None, scope: str = "all"):
    stmt = select(ProcessInstance).order_by(ProcessInstance.id.desc())
    if scope == "mine":
        stmt = stmt.where(ProcessInstance.started_by_id == user.id)
    if status:
        stmt = stmt.where(ProcessInstance.status == status)
    if definition_id:
        stmt = stmt.where(ProcessInstance.definition_id == definition_id)
    if q:
        stmt = stmt.where(or_(ProcessInstance.title.contains(q), ProcessInstance.business_key.contains(q)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for i in rows:
        d = db.get(ProcessDefinition, i.definition_id)
        open_tasks = db.scalar(select(func.count()).select_from(EngineTask).where(
            EngineTask.instance_id == i.id, EngineTask.status.in_(["ready", "claimed"])))
        items.append({
            "id": i.id, "title": i.title, "business_key": i.business_key, "status": i.status,
            "process": {"id": d.id, "title": d.title, "key": d.key} if d else None,
            "version": i.version.version if i.version else None,
            "started_by_id": i.started_by_id,
            "started_at": i.started_at.isoformat() if i.started_at else None,
            "started_at_jalali": gregorian_to_jalali_str(i.started_at, with_time=True),
            "finished_at": i.finished_at.isoformat() if i.finished_at else None,
            "open_tasks": open_tasks,
        })
    return {"items": items, "total": total}


@router.get("/process-instances/{iid}")
def get_instance(iid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    i = db.get(ProcessInstance, iid)
    if not i:
        raise HTTPException(404, "نمونه یافت نشد")
    d = db.get(ProcessDefinition, i.definition_id)
    tasks = db.scalars(select(EngineTask).where(EngineTask.instance_id == iid).order_by(EngineTask.id)).all()
    events = db.scalars(select(InstanceEvent).where(InstanceEvent.instance_id == iid).order_by(InstanceEvent.id)).all()
    incidents = db.scalars(select(Incident).where(Incident.instance_id == iid, Incident.resolved_at.is_(None))).all()
    users = {u.id: u.full_name for u in db.scalars(select(User)).all()}
    return {
        "id": i.id, "title": i.title, "business_key": i.business_key, "status": i.status,
        "process": {"id": d.id, "title": d.title, "key": d.key} if d else None,
        "version_id": i.version_id, "version": i.version.version if i.version else None,
        "started_by_id": i.started_by_id,
        "started_by": users.get(i.started_by_id),
        "started_at": i.started_at.isoformat() if i.started_at else None,
        "started_at_jalali": gregorian_to_jalali_str(i.started_at, with_time=True),
        "finished_at": i.finished_at.isoformat() if i.finished_at else None,
        "tasks": [{
            "id": t.id, "spec_id": t.spec_id, "name": t.name, "status": t.status,
            "assignee_id": t.assignee_id, "assignee": users.get(t.assignee_id),
            "candidate_role": t.candidate_role, "claimed_by_id": t.claimed_by_id,
            "result": t.result, "comment": t.comment,
            "due_at": t.due_at.isoformat() if t.due_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        } for t in tasks],
        "history": [{
            "id": e.id, "event_type": e.event_type, "spec_id": e.spec_id, "task_name": e.task_name,
            "actor": users.get(e.actor_id), "comment": e.comment, "detail": e.detail_json,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "created_at_jalali": gregorian_to_jalali_str(e.created_at, with_time=True),
        } for e in events],
        "incidents": [{
            "id": x.id, "spec_id": x.spec_id, "message": x.message,
            "created_at": x.created_at.isoformat() if x.created_at else None,
        } for x in incidents],
    }


@router.get("/process-instances/{iid}/state")
def instance_state(iid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """وضعیت زنده برای نمایش نمودار: عناصر فعال/انجام‌شده/خطادار."""
    i = db.get(ProcessInstance, iid)
    if not i:
        raise HTTPException(404, "نمونه یافت نشد")
    try:
        wf = svc.load_workflow(i)
    except Exception:
        wf = None
    active, errored = [], []
    if wf is not None:
        active = [t.task_spec.name for t in adapter.ready_user_tasks(wf)]
        errored = [t.task_spec.name for t in adapter.error_tasks(wf)]
    completed = [e.spec_id for e in db.scalars(select(InstanceEvent).where(
        InstanceEvent.instance_id == iid, InstanceEvent.event_type == "task_completed")).all() if e.spec_id]
    # رویدادهای آغاز/پایان
    started = [e.spec_id for e in db.scalars(select(InstanceEvent).where(
        InstanceEvent.instance_id == iid, InstanceEvent.event_type == "instance_started")).all()]
    return {"active": active, "completed": completed, "error": errored, "started": started,
            "status": i.status}


@router.post("/process-instances/{iid}/cancel")
def cancel_instance(iid: int, body: dict, db: Session = Depends(get_db), user: User = Depends(require_perm("instance.manage")), request: Request = None):
    i = db.get(ProcessInstance, iid)
    if not i:
        raise HTTPException(404, "نمونه یافت نشد")
    try:
        svc.cancel_instance(db, i, user, reason=body.get("reason", ""))
    except ValueError as e:
        raise HTTPException(400, e.args[0])
    log_action(db, user.id, "instance.cancelled", "instance", iid, {}, request)
    return {"ok": True}


@router.post("/process-instances/{iid}/tick")
def tick_instance(iid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """بررسی تایمرهای این نمونه (برای نمایش وضعیت به‌روز)."""
    i = db.get(ProcessInstance, iid)
    if not i:
        raise HTTPException(404, "نمونه یافت نشد")
    svc.tick(db, limit=1)
    return {"ok": True}


@router.post("/incidents/{incident_id}/retry")
def retry_incident(incident_id: int, db: Session = Depends(get_db), user: User = Depends(require_perm("instance.manage")), request: Request = None):
    """رسیدگی کنترل‌شده به خطا: اصلاح شرایط و تلاش مجدد فعالیت خطادار (AC-15)."""
    x = db.get(Incident, incident_id)
    if not x:
        raise HTTPException(404, "مورد یافت نشد")
    try:
        svc.retry_incident(db, x, user)
    except ValueError as e:
        raise HTTPException(400, e.args[0])
    log_action(db, user.id, "incident.retried", "incident", incident_id, {}, request)
    return {"ok": True}


@router.post("/engine/tick")
def engine_tick(db: Session = Depends(get_db), user: User = Depends(require_perm("monitor.view"))):
    """زمان‌بند سبک — بررسی نمونه‌های در جریان (در عملیات به Worker منتقل می‌شود)."""
    touched = svc.tick(db)
    return {"touched": touched}
