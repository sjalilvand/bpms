# -*- coding: utf-8 -*-
"""API بانک سازمانی (فاز ۸) — فیلدهای سازمانی، بانک فرم‌ها و بانک فرایندها.

قابلیت‌ها:
- CRUD کامل برای سه موجودیت (فیلد / الگوی فرم / الگوی فرایند)
- «ایجاد فرم از الگو» و «ایجاد فرایند از الگو» با یک کلیک
- «افزودن فرم موجود به بانک» برای نسخه منتشرشده/آخرین نسخه
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_perm
from app.modules.identity.models import User
from app.modules.forms.models import FormDefinition, FormVersion
from app.modules.engine.models import ProcessDefinition, ProcessVersion
from app.modules.audit.service import log_action
from .models import OrgField, FormTemplate, ProcessTemplate

router = APIRouter()


# ---------- Schemas ----------
class OrgFieldIn(BaseModel):
    key: str = Field(min_length=2, max_length=80)
    label: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=2, max_length=40)
    category: str = ""
    description: str = ""
    config_json: dict = {}


class FormTemplateIn(BaseModel):
    key: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    category: str = ""
    schema_json: dict


class ProcessTemplateIn(BaseModel):
    key: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    category: str = ""
    bpmn_xml: str
    main_process_id: str = ""
    config_json: dict = {}


class InstantiateFormIn(BaseModel):
    key: str
    title: str = ""


class InstantiateProcessIn(BaseModel):
    key: str
    title: str = ""


# ---------- فیلدهای سازمانی ----------
def org_field_out(f: OrgField):
    return {
        "id": f.id, "key": f.key, "label": f.label, "type": f.type,
        "category": f.category or "", "description": f.description or "",
        "config_json": f.config_json or {},
    }


@router.get("/library/fields")
def list_org_fields(db: Session = Depends(get_db), user: User = Depends(get_current_user), q: str = ""):
    stmt = select(OrgField).order_by(OrgField.id.desc())
    if q:
        stmt = stmt.where(OrgField.label.contains(q) | OrgField.key.contains(q))
    return {"items": [org_field_out(f) for f in db.scalars(stmt).all()]}


@router.post("/library/fields")
def create_org_field(body: OrgFieldIn, db: Session = Depends(get_db),
                     user: User = Depends(require_perm("form.manage")), request: Request = None):
    if db.scalar(select(OrgField).where(OrgField.key == body.key)):
        raise HTTPException(400, "فیلد سازمانی با این کلید از قبل ثبت شده است")
    f = OrgField(key=body.key, label=body.label, type=body.type, category=body.category,
                 description=body.description, config_json=body.config_json or {}, created_by_id=user.id)
    db.add(f)
    db.commit()
    log_action(db, user.id, "library.field_created", "org_field", f.id, {"key": f.key}, request)
    return org_field_out(f)


@router.put("/library/fields/{fid}")
def update_org_field(fid: int, body: OrgFieldIn, db: Session = Depends(get_db),
                     user: User = Depends(require_perm("form.manage")), request: Request = None):
    f = db.get(OrgField, fid)
    if not f:
        raise HTTPException(404, "فیلد سازمانی یافت نشد")
    dup = db.scalar(select(OrgField).where(OrgField.key == body.key, OrgField.id != fid))
    if dup:
        raise HTTPException(400, "کلید تکراری است")
    f.key, f.label, f.type = body.key, body.label, body.type
    f.category, f.description, f.config_json = body.category, body.description, body.config_json or {}
    db.commit()
    log_action(db, user.id, "library.field_updated", "org_field", f.id, {}, request)
    return org_field_out(f)


@router.delete("/library/fields/{fid}")
def delete_org_field(fid: int, db: Session = Depends(get_db),
                     user: User = Depends(require_perm("form.manage")), request: Request = None):
    f = db.get(OrgField, fid)
    if not f:
        raise HTTPException(404, "فیلد سازمانی یافت نشد")
    db.delete(f)
    db.commit()
    log_action(db, user.id, "library.field_deleted", "org_field", fid, {}, request)
    return {"ok": True}


# ---------- بانک فرم‌های سازمانی ----------
def form_template_out(t: FormTemplate):
    fields = (t.schema_json or {}).get("fields", [])
    return {
        "id": t.id, "key": t.key, "title": t.title, "description": t.description or "",
        "category": t.category or "", "field_count": len(fields),
        "fields_preview": [
            {"key": f.get("key"), "label": f.get("label"), "type": f.get("type")}
            for f in fields[:8] if isinstance(f, dict)
        ],
    }


@router.get("/library/forms")
def list_form_templates(db: Session = Depends(get_db), user: User = Depends(get_current_user), q: str = ""):
    stmt = select(FormTemplate).order_by(FormTemplate.id.desc())
    if q:
        stmt = stmt.where(FormTemplate.title.contains(q) | FormTemplate.key.contains(q))
    return {"items": [form_template_out(t) for t in db.scalars(stmt).all()]}


@router.get("/library/forms/{tid}")
def get_form_template(tid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.get(FormTemplate, tid)
    if not t:
        raise HTTPException(404, "الگوی فرم یافت نشد")
    return {"id": t.id, "key": t.key, "title": t.title, "description": t.description or "",
            "category": t.category or "", "schema_json": t.schema_json}


@router.post("/library/forms")
def create_form_template(body: FormTemplateIn, db: Session = Depends(get_db),
                         user: User = Depends(require_perm("form.manage")), request: Request = None):
    if db.scalar(select(FormTemplate).where(FormTemplate.key == body.key)):
        raise HTTPException(400, "الگوی فرم با این کلید از قبل ثبت شده است")
    t = FormTemplate(key=body.key, title=body.title, description=body.description,
                     category=body.category, schema_json=body.schema_json, created_by_id=user.id)
    db.add(t)
    db.commit()
    log_action(db, user.id, "library.form_template_created", "form_template", t.id, {"key": t.key}, request)
    return form_template_out(t)


@router.post("/library/forms/from-existing/{form_id}")
def add_form_to_library(form_id: int, body: dict, db: Session = Depends(get_db),
                        user: User = Depends(require_perm("form.manage")), request: Request = None):
    """افزودن فرم موجود (آخرین نسخه) به بانک سازمانی — body: {key?, category?, description?}"""
    f = db.get(FormDefinition, form_id)
    if not f:
        raise HTTPException(404, "فرم یافت نشد")
    v = f.versions[0] if f.versions else None
    if not v:
        raise HTTPException(400, "این فرم هیچ نسخه‌ای ندارد")
    key = (body.get("key") or f"form_{f.key}").strip()
    if db.scalar(select(FormTemplate).where(FormTemplate.key == key)):
        raise HTTPException(400, "الگویی با این کلید از قبل در بانک ثبت شده است")
    t = FormTemplate(key=key, title=body.get("title") or f.title,
                     description=body.get("description") or f.description or "",
                     category=body.get("category") or "", schema_json=v.schema_json or {"fields": []},
                     created_by_id=user.id)
    db.add(t)
    db.commit()
    log_action(db, user.id, "library.form_added_from_existing", "form_template", t.id, {"source_form": f.id}, request)
    return form_template_out(t)


@router.delete("/library/forms/{tid}")
def delete_form_template(tid: int, db: Session = Depends(get_db),
                         user: User = Depends(require_perm("form.manage")), request: Request = None):
    t = db.get(FormTemplate, tid)
    if not t:
        raise HTTPException(404, "الگوی فرم یافت نشد")
    db.delete(t)
    db.commit()
    log_action(db, user.id, "library.form_template_deleted", "form_template", tid, {}, request)
    return {"ok": True}


@router.post("/library/forms/{tid}/instantiate")
def instantiate_form(tid: int, body: InstantiateFormIn, db: Session = Depends(get_db),
                     user: User = Depends(require_perm("form.manage")), request: Request = None):
    """ساخت فرم جدید از الگوی بانک — پیش‌نویس آماده ویرایش."""
    t = db.get(FormTemplate, tid)
    if not t:
        raise HTTPException(404, "الگوی فرم یافت نشد")
    if db.scalar(select(FormDefinition).where(FormDefinition.key == body.key)):
        raise HTTPException(400, "فرم با این کلید از قبل وجود دارد")
    import copy
    f = FormDefinition(key=body.key, title=body.title or t.title,
                       description=t.description or "", created_by_id=user.id)
    db.add(f)
    db.flush()
    v = FormVersion(form_id=f.id, version=1, schema_json=copy.deepcopy(t.schema_json),
                    created_by_id=user.id, change_note=f"ایجاد از بانک سازمانی «{t.title}»")
    db.add(v)
    db.commit()
    log_action(db, user.id, "library.form_instantiated", "form", f.id, {"template": t.key}, request)
    return {"id": f.id, "version_id": v.id}


# ---------- بانک فرایندهای سازمانی ----------
def process_template_out(t: ProcessTemplate):
    return {
        "id": t.id, "key": t.key, "title": t.title, "description": t.description or "",
        "category": t.category or "", "main_process_id": t.main_process_id or "",
        "has_bindings": bool((t.config_json or {}).get("bindings")),
    }


@router.get("/library/processes")
def list_process_templates(db: Session = Depends(get_db), user: User = Depends(get_current_user), q: str = ""):
    stmt = select(ProcessTemplate).order_by(ProcessTemplate.id.desc())
    if q:
        stmt = stmt.where(ProcessTemplate.title.contains(q) | ProcessTemplate.key.contains(q))
    return {"items": [process_template_out(t) for t in db.scalars(stmt).all()]}


@router.post("/library/processes")
def create_process_template(body: ProcessTemplateIn, db: Session = Depends(get_db),
                            user: User = Depends(require_perm("process.manage")), request: Request = None):
    if db.scalar(select(ProcessTemplate).where(ProcessTemplate.key == body.key)):
        raise HTTPException(400, "الگوی فرایند با این کلید از قبل ثبت شده است")
    t = ProcessTemplate(key=body.key, title=body.title, description=body.description,
                        category=body.category, bpmn_xml=body.bpmn_xml,
                        main_process_id=body.main_process_id, config_json=body.config_json or {},
                        created_by_id=user.id)
    db.add(t)
    db.commit()
    log_action(db, user.id, "library.process_template_created", "process_template", t.id, {"key": t.key}, request)
    return process_template_out(t)


@router.post("/library/processes/from-existing/{pid}")
def add_process_to_library(pid: int, body: dict, db: Session = Depends(get_db),
                           user: User = Depends(require_perm("process.manage")), request: Request = None):
    """افزودن فرایند موجود (آخرین نسخه) به بانک سازمانی — body: {key?, category?, description?}"""
    p = db.get(ProcessDefinition, pid)
    if not p:
        raise HTTPException(404, "فرایند یافت نشد")
    v = p.versions[0] if p.versions else None
    if not v:
        raise HTTPException(400, "این فرایند هیچ نسخه‌ای ندارد")
    key = (body.get("key") or f"process_{p.key}").strip()
    if db.scalar(select(ProcessTemplate).where(ProcessTemplate.key == key)):
        raise HTTPException(400, "الگویی با این کلید از قبل در بانک ثبت شده است")
    # اگر XML جاریِ طراح ارسال شده باشد همان ذخیره می‌شود؛ وگرنه آخرین نسخه ذخیره‌شده
    bpmn_xml = body.get("bpmn_xml") or v.bpmn_xml
    main_pid = body.get("main_process_id") or v.main_process_id or ""
    t = ProcessTemplate(key=key, title=body.get("title") or p.title,
                        description=body.get("description") or p.description or "",
                        category=body.get("category") or "", bpmn_xml=bpmn_xml,
                        main_process_id=main_pid, config_json=v.config_json or {},
                        created_by_id=user.id)
    db.add(t)
    db.commit()
    log_action(db, user.id, "library.process_added_from_existing", "process_template", t.id, {"source_process": p.id}, request)
    return process_template_out(t)


@router.delete("/library/processes/{tid}")
def delete_process_template(tid: int, db: Session = Depends(get_db),
                            user: User = Depends(require_perm("process.manage")), request: Request = None):
    t = db.get(ProcessTemplate, tid)
    if not t:
        raise HTTPException(404, "الگوی فرایند یافت نشد")
    db.delete(t)
    db.commit()
    log_action(db, user.id, "library.process_template_deleted", "process_template", tid, {}, request)
    return {"ok": True}


@router.post("/library/processes/{tid}/instantiate")
def instantiate_process(tid: int, body: InstantiateProcessIn, db: Session = Depends(get_db),
                        user: User = Depends(require_perm("process.manage")), request: Request = None):
    """ساخت فرایند جدید از الگوی بانک — نسخه اول به‌صورت پیش‌نویس (شامل اتصال فرم‌ها و مسئول‌ها)."""
    import copy
    t = db.get(ProcessTemplate, tid)
    if not t:
        raise HTTPException(404, "الگوی فرایند یافت نشد")
    if db.scalar(select(ProcessDefinition).where(ProcessDefinition.key == body.key)):
        raise HTTPException(400, "فرایند با این کلید از قبل وجود دارد")
    p = ProcessDefinition(key=body.key, title=body.title or t.title,
                          description=t.description or "", created_by_id=user.id)
    db.add(p)
    db.flush()
    v = ProcessVersion(definition_id=p.id, version=1, bpmn_xml=t.bpmn_xml,
                       main_process_id=t.main_process_id or "",
                       config_json=copy.deepcopy(t.config_json or {}),
                       created_by_id=user.id,
                       change_note=f"ایجاد از بانک سازمانی «{t.title}»")
    db.add(v)
    db.commit()
    log_action(db, user.id, "library.process_instantiated", "process", p.id, {"template": t.key}, request)
    return {"id": p.id, "version_id": v.id}
