# -*- coding: utf-8 -*-
"""فاز ۵ — API بیرونی سامانه (مصرف سرویس‌های دیگر سازمان) با کلید، امضا و idempotency.

مسیرها: /external/v1/... — احراز با X-API-Key (+ امضای HMAC اختیاری per-client) و
دامنه‌های صریح (scopes). عملیات نوشتاری با هدر Idempotency-Key تکرارپذیرند:
پاسخ اولین اجرا ذخیره و در تکرارِ همان درخواست بازپخش می‌شود؛ با محتوای متفاوت → 409.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.engine import service as engine_svc
from app.modules.engine.models import ProcessDefinition, ProcessVersion, ProcessInstance, EngineTask
from app.modules.external import service as ext
from app.modules.external.models import ExternalClient
from app.modules.identity.models import User

router = APIRouter()

SCOPES = ["instances.start", "instances.read", "tasks.complete"]


def _actor_user(db: Session, client: ExternalClient) -> User:
    """کاربر نماینده فراخوانی‌های بیرونی: actor_username سرویس، وگرنه نخستین مدیر سامانه."""
    if client.actor_username:
        u = db.scalar(select(User).where(User.username == client.actor_username))
        if u and u.is_active:
            return u
        raise HTTPException(400, f"کاربر نماینده «{client.actor_username}» یافت نشد یا غیرفعال است")
    u = db.scalar(select(User).where(User.is_superadmin.is_(True)).order_by(User.id))
    if not u:
        raise HTTPException(500, "کاربر نماینده‌ای برای API بیرونی تعریف نشده است")
    return u


class ExternalStartIn(BaseModel):
    definition_key: str | None = None
    definition_id: int | None = None
    version_id: int | None = None
    data: dict = {}
    business_key: str | None = None
    title: str | None = None


class ExternalCompleteIn(BaseModel):
    data: dict = {}
    result: str | None = None
    comment: str | None = None


@router.post("/external/v1/process-instances")
async def ext_start(request: Request, body: ExternalStartIn, db: Session = Depends(get_db)):
    raw = await request.body()
    client = ext.authenticate(db, request, raw, "instances.start")
    fp = ext.fingerprint("POST", "/api/v1/external/v1/process-instances", raw)
    idem_key = request.headers.get("Idempotency-Key", "")
    replay = ext.lookup_idempotent(db, client, idem_key, fp, "process-instances.start")
    if replay:
        return _replay(replay)

    # یافتن نسخه منتشرشده
    if body.version_id:
        v = db.get(ProcessVersion, body.version_id)
        if not v or v.status != "published":
            raise HTTPException(400, "نسخه یافت نشد یا منتشرشده نیست")
    else:
        d = None
        if body.definition_id:
            d = db.get(ProcessDefinition, body.definition_id)
        elif body.definition_key:
            d = db.scalar(select(ProcessDefinition).where(ProcessDefinition.key == body.definition_key))
        else:
            raise HTTPException(400, "definition_key یا definition_id الزامی است")
        if not d:
            raise HTTPException(404, "فرایند یافت نشد")
        v = d.latest_published
        if not v:
            raise HTTPException(400, "نسخه منتشرشده‌ای برای این فرایند وجود ندارد")
    try:
        inst = engine_svc.start_instance(db, v, _actor_user(db, client), data=body.data,
                                         business_key=body.business_key, title=body.title)
    except ValueError as e:
        raise HTTPException(400, e.args[0])
    out = {"id": inst.id, "title": inst.title, "status": inst.status,
           "business_key": inst.business_key, "version": v.version}
    ext.store_idempotent(db, client, idem_key, fp, "process-instances.start", 200, out)
    db.commit()
    return out


def _replay(replay: dict):
    from fastapi import Response
    resp = Response(content=ext.safe_json_bytes(replay["body"]), media_type="application/json")
    resp.headers["X-Idempotent-Replay"] = "true"
    resp.status_code = replay["status"]
    return resp


@router.get("/external/v1/process-instances/{iid}")
def ext_status(iid: int, request: Request, db: Session = Depends(get_db)):
    client = ext.authenticate(db, request, b"", "instances.read")
    i = db.get(ProcessInstance, iid)
    if not i:
        raise HTTPException(404, "نمونه یافت نشد")
    tasks = db.scalars(select(EngineTask).where(EngineTask.instance_id == iid).order_by(EngineTask.id)).all()
    return {
        "id": i.id, "title": i.title, "status": i.status, "business_key": i.business_key,
        "started_at": i.started_at.isoformat() if i.started_at else None,
        "finished_at": i.finished_at.isoformat() if i.finished_at else None,
        "open_tasks": [{"id": t.id, "name": t.name, "spec_id": t.spec_id, "status": t.status,
                        "due_at": t.due_at.isoformat() if t.due_at else None}
                       for t in tasks if t.status in ("ready", "claimed")],
    }


@router.post("/external/v1/tasks/{task_id}/complete")
async def ext_complete(task_id: int, request: Request, body: ExternalCompleteIn, db: Session = Depends(get_db)):
    raw = await request.body()
    client = ext.authenticate(db, request, raw, "tasks.complete")
    fp = ext.fingerprint("POST", f"/api/v1/external/v1/tasks/{task_id}/complete", raw)
    idem_key = request.headers.get("Idempotency-Key", "")
    replay = ext.lookup_idempotent(db, client, idem_key, fp, "tasks.complete")
    if replay:
        return _replay(replay)

    task = db.get(EngineTask, task_id)
    if not task:
        raise HTTPException(404, "وظیفه یافت نشد")
    try:
        done = engine_svc.complete_task(db, task, _actor_user(db, client),
                                        data=body.data or None, result=body.result, comment=body.comment)
    except ValueError as e:
        raise HTTPException(400, e.args[0])
    out = {"id": done.id, "status": done.status, "result": done.result,
           "instance_id": done.instance_id}
    ext.store_idempotent(db, client, idem_key, fp, "tasks.complete", 200, out)
    db.commit()
    return out
