# -*- coding: utf-8 -*-
"""API فرایندها: تعریف، نسخه BPMN، اعتبارسنجی پیش از انتشار و انتشار نسخه.

اعتبارسنجی انتشار شامل: ساختار XML، پارس موتور، یکتایی شناسه‌ها، وجود فرایند اصلی،
فرم‌های متصل و هشدارهای تفکیک‌شده از خطاها (سند §۷.۳ و AC-02).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_perm
from app.modules.identity.models import User, utcnow
from app.modules.engine import adapter
from app.modules.engine.models import ProcessDefinition, ProcessVersion, ProcessInstance
from app.modules.forms.models import FormDefinition, FormVersion
from app.modules.audit.service import log_action

router = APIRouter()


class ProcessIn(BaseModel):
    key: str
    title: str
    description: str = ""


class VersionIn(BaseModel):
    bpmn_xml: str
    main_process_id: str = ""
    config_json: dict = {}
    change_note: str = ""


def version_out(v: ProcessVersion, include_xml: bool = False):
    d = {
        "id": v.id, "definition_id": v.definition_id, "version": v.version,
        "main_process_id": v.main_process_id, "config_json": v.config_json or {},
        "status": v.status, "change_note": v.change_note,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "published_at": v.published_at.isoformat() if v.published_at else None,
    }
    if include_xml:
        d["bpmn_xml"] = v.bpmn_xml
    return d


def definition_out(p: ProcessDefinition):
    latest = p.versions[0] if p.versions else None
    pub = p.latest_published
    return {
        "id": p.id, "key": p.key, "title": p.title, "description": p.description,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "latest_version": version_out(latest) if latest else None,
        "published_version": version_out(pub) if pub else None,
    }


@router.get("/processes")
def list_processes(db: Session = Depends(get_db), user: User = Depends(get_current_user), q: str = ""):
    stmt = select(ProcessDefinition).order_by(ProcessDefinition.id.desc())
    if q:
        stmt = stmt.where(ProcessDefinition.title.contains(q))
    rows = db.scalars(stmt).all()
    return {"items": [definition_out(p) for p in rows]}


@router.post("/processes")
def create_process(body: ProcessIn, db: Session = Depends(get_db), user: User = Depends(require_perm("process.manage")), request: Request = None):
    if db.scalar(select(ProcessDefinition).where(ProcessDefinition.key == body.key)):
        raise HTTPException(400, "کلید فرایند تکراری است")
    p = ProcessDefinition(key=body.key, title=body.title, description=body.description, created_by_id=user.id)
    db.add(p)
    db.commit()
    log_action(db, user.id, "process.created", "process", p.id, {"key": p.key}, request)
    return {"id": p.id}


@router.put("/processes/{pid}")
def update_process(pid: int, body: ProcessIn, db: Session = Depends(get_db), user: User = Depends(require_perm("process.manage")), request: Request = None):
    p = db.get(ProcessDefinition, pid)
    if not p:
        raise HTTPException(404, "فرایند یافت نشد")
    p.title, p.description = body.title, body.description
    db.commit()
    log_action(db, user.id, "process.updated", "process", p.id, {}, request)
    return {"ok": True}


@router.get("/processes/{pid}")
def get_process(pid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(ProcessDefinition, pid)
    if not p:
        raise HTTPException(404, "فرایند یافت نشد")
    out = definition_out(p)
    out["versions"] = [version_out(v) for v in p.versions]
    return out


class ParseIn(BaseModel):
    bpmn_xml: str


@router.post("/processes/parse-ids")
def parse_ids(body: ParseIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """فهرست فرایندهای داخل فایل BPMN برای انتخاب فرایند اصلی."""
    try:
        items = adapter.list_process_ids(body.bpmn_xml)
    except adapter.EngineParseError as e:
        raise HTTPException(400, str(e))
    return {"items": items}


@router.post("/processes/{pid}/versions")
def create_version(pid: int, body: VersionIn, db: Session = Depends(get_db), user: User = Depends(require_perm("process.manage")), request: Request = None):
    p = db.get(ProcessDefinition, pid)
    if not p:
        raise HTTPException(404, "فرایند یافت نشد")
    main = body.main_process_id
    try:
        procs = adapter.list_process_ids(body.bpmn_xml)
    except adapter.EngineParseError as e:
        raise HTTPException(400, str(e))
    if not procs:
        raise HTTPException(400, "هیچ فرایندی در فایل یافت نشد")
    if not main:
        exe = [x for x in procs if x["isExecutable"] == "true"]
        main = (exe[0] if exe else procs[0])["id"]
    if main not in [x["id"] for x in procs]:
        raise HTTPException(400, "فرایند اصلی انتخابی در فایل وجود ندارد")
    last = db.scalar(select(ProcessVersion).where(ProcessVersion.definition_id == pid).order_by(ProcessVersion.version.desc()))
    v = ProcessVersion(definition_id=pid, version=(last.version + 1) if last else 1,
                       bpmn_xml=body.bpmn_xml, main_process_id=main,
                       config_json=body.config_json or {}, created_by_id=user.id, change_note=body.change_note)
    db.add(v)
    db.commit()
    log_action(db, user.id, "process.version_created", "process", pid, {"version": v.version}, request)
    return version_out(v)


@router.put("/processes/versions/{vid}")
def update_version(vid: int, body: VersionIn, db: Session = Depends(get_db), user: User = Depends(require_perm("process.manage"))):
    v = db.get(ProcessVersion, vid)
    if not v:
        raise HTTPException(404, "نسخه یافت نشد")
    if v.status != "draft":
        raise HTTPException(400, "نسخه منتشرشده قابل ویرایش نیست؛ نسخه جدید بسازید")
    v.bpmn_xml = body.bpmn_xml
    if body.main_process_id:
        v.main_process_id = body.main_process_id
    v.config_json = body.config_json or v.config_json
    v.change_note = body.change_note
    db.commit()
    return version_out(v)


@router.get("/processes/versions/{vid}")
def get_version(vid: int, include_xml: bool = True, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    v = db.get(ProcessVersion, vid)
    if not v:
        raise HTTPException(404, "نسخه یافت نشد")
    out = version_out(v, include_xml=include_xml)
    out["process"] = {"id": v.definition.id, "key": v.definition.key, "title": v.definition.title}
    return out


@router.post("/processes/versions/{vid}/validate")
def validate_version(vid: int, db: Session = Depends(get_db), user: User = Depends(require_perm("process.manage"))):
    v = db.get(ProcessVersion, vid)
    if not v:
        raise HTTPException(404, "نسخه یافت نشد")
    return _validate(db, v)


def _validate(db: Session, v: ProcessVersion) -> dict:
    errors, warnings = [], []
    # ۱) ساختار XML و پارس موتور
    try:
        procs = adapter.list_process_ids(v.bpmn_xml)
        if not procs:
            errors.append("هیچ فرایندی در فایل تعریف نشده است")
    except adapter.EngineParseError as e:
        return {"errors": [str(e)], "warnings": []}
    if v.main_process_id not in [x["id"] for x in procs]:
        errors.append("فرایند اصلی انتخابی در فایل وجود ندارد")
    # ۲) پارس موتور — ساختار، مراجع و قواعد معنایی
    try:
        spec = adapter.parse_spec(v.bpmn_xml, v.main_process_id)
        spec_ids = set(spec.task_specs.keys())
    except adapter.EngineParseError as e:
        return {"errors": [str(e)], "warnings": []}
    # ۳) اتصال‌ها: فعالیت‌های کاربر بدون فرم → هشدار؛ بدون مسئول → هشدار
    bindings = (v.config_json or {}).get("bindings", {})
    user_tasks = []
    for tid, ts in spec.task_specs.items():
        cls = ts.__class__.__name__
        if cls == "UserTask":
            user_tasks.append(tid)
    for tid in user_tasks:
        b = bindings.get(tid) or {}
        if not b.get("formDefinitionId"):
            warnings.append(f"فعالیت «{tid}» فرم متصل ندارد")
        if not b.get("assigneeType"):
            warnings.append(f"فعالیت «{tid}» مسئول تعیین‌شده ندارد")
    # ۴) فرم‌های متصل منتشرشده باشند
    for tid, b in (bindings or {}).items():
        fid = b.get("formDefinitionId")
        if fid:
            f = db.get(FormDefinition, fid)
            if not f:
                errors.append(f"اتصال «{tid}»: فرم یافت نشد")
            elif not f.latest_published:
                errors.append(f"اتصال «{tid}»: فرم «{f.title}» نسخه منتشرشده ندارد")
        # نتایج تعریف‌شده
        results = b.get("results") or []
        values = [r.get("value") for r in results if r.get("value")]
        if len(values) != len(set(values)):
            errors.append(f"اتصال «{tid}»: مقادیر نتیجه تکراری است")
    # ۵) شناسه‌های تکراری در XML
    import re as _re
    ids = _re.findall(r'id="([^"]+)"', v.bpmn_xml)
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        errors.append(f"شناسه‌های تکراری در مدل: {', '.join(sorted(dupes)[:5])}")
    # ۶) عنصر اجرایی پشتیبانی‌نشده
    unsupported = {"CallActivity"}  # محدودیت‌های موتور در docs/bpmn-coverage.md
    try:
        root_cls = {ts.__class__.__name__ for ts in spec.task_specs.values()}
        for cls in root_cls:
            if cls in unsupported:
                errors.append(f"عنصر «{cls}» در این نسخه پشتیبانی اجرایی ندارد و انتشار باید پس از حذف آن انجام شود")
    except Exception:
        pass
    return {"errors": errors, "warnings": warnings}


@router.post("/processes/versions/{vid}/publish")
def publish_version(vid: int, db: Session = Depends(get_db), user: User = Depends(require_perm("process.publish")), request: Request = None):
    v = db.get(ProcessVersion, vid)
    if not v:
        raise HTTPException(404, "نسخه یافت نشد")
    if v.status == "published":
        raise HTTPException(400, "این نسخه قبلاً منتشر شده است")
    res = _validate(db, v)
    if res["errors"]:
        raise HTTPException(400, {"message": "انتشار به‌دلیل خطای قطعی مجاز نیست (AC-02)", **res})
    v.status = "published"
    v.published_at = utcnow()
    v.published_by_id = user.id
    db.commit()
    log_action(db, user.id, "process.published", "process_version", v.id,
               {"process": v.definition_id, "version": v.version, "warnings": res["warnings"]}, request)
    return {"ok": True, "warnings": res["warnings"]}


@router.delete("/processes/{pid}")
def delete_process(pid: int, db: Session = Depends(get_db), user: User = Depends(require_perm("process.manage")), request: Request = None):
    p = db.get(ProcessDefinition, pid)
    if not p:
        raise HTTPException(404, "فرایند یافت نشد")
    used = db.scalar(select(func.count()).select_from(ProcessInstance).where(ProcessInstance.definition_id == pid))
    if used:
        raise HTTPException(400, "این فرایند نمونه اجرایی دارد و حذف آن مجاز نیست")
    db.delete(p)
    db.commit()
    log_action(db, user.id, "process.deleted", "process", pid, {}, request)
    return {"ok": True}
