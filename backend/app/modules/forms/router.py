# -*- coding: utf-8 -*-
"""API فرم‌ساز: تعریف فرم، نسخه‌ها، انتشار، اعتبارسنجی ساختاری و داده."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_perm
from app.modules.identity.models import User, utcnow
from app.modules.forms.models import FormDefinition, FormVersion, FormSubmission
from app.modules.forms.validator import validate_form_data
from app.modules.forms.safeeval import evaluate_formula
from app.modules.audit.service import log_action

router = APIRouter()

KNOWN_TYPES = {
    "text", "textarea", "number", "integer", "money", "percent",
    "date", "jalali_date", "time", "national_id", "mobile", "email",
    "select", "multiselect", "checkbox", "checkgroup", "radio",
    "user", "org_unit", "file", "image", "attachment_list",
    "calculated", "subform", "subform_single",
    "title", "help", "divider", "summary",
}

# امکان استفاده مجدد از گروه‌های CheckBox و RadioGroup با جدول پایه (قاعده سند §۱۵.۲)
LOOKUP_CAPABLE = {"select", "multiselect", "checkgroup", "radio"}


class FormIn(BaseModel):
    key: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=200)
    description: str = ""


class SchemaIn(BaseModel):
    title: str | None = None
    fields: list[dict] = []


class VersionIn(BaseModel):
    schema_json: SchemaIn
    change_note: str = ""


def version_out(v: FormVersion, include_schema: bool = False):
    d = {
        "id": v.id, "form_id": v.form_id, "version": v.version, "status": v.status,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "change_note": v.change_note,
    }
    if include_schema:
        d["schema_json"] = v.schema_json
    return d


def form_out(f: FormDefinition):
    latest = f.versions[0] if f.versions else None
    pub = f.latest_published
    return {
        "id": f.id, "key": f.key, "title": f.title, "description": f.description,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "latest_version": version_out(latest) if latest else None,
        "published_version": version_out(pub) if pub else None,
    }


def validate_schema_structure(db: Session, schema: dict) -> tuple[list[str], list[str]]:
    """اعتبارسنجی تعریف فرم پیش از انتشار — خطاها و هشدارها تفکیک می‌شوند."""
    errors, warnings = [], []
    fields = schema.get("fields", [])
    keys = [f.get("key") for f in fields if f.get("key")]
    dupes = {k for k in keys if keys.count(k) > 1}
    if dupes:
        errors.append(f"نام فنی فیلدها باید یکتا باشد؛ تکراری: {', '.join(sorted(dupes))}")
    for f in fields:
        key = f.get("key", "؟")
        ftype = f.get("type")
        if ftype not in KNOWN_TYPES:
            errors.append(f"فیلد «{key}»: نوع «{ftype}» پشتیبانی نمی‌شود")
            continue
        if ftype not in ("title", "help", "divider", "summary", "calculated") and not f.get("key"):
            errors.append("فیلد بدون نام فنی یافت شد")
        if f.get("lookupId"):
            from app.modules.lookups.router import LookupDefinition
            if not db.get(LookupDefinition, f["lookupId"]):
                errors.append(f"فیلد «{key}»: جدول پایه یافت نشد")
        if ftype in ("subform", "subform_single"):
            sub_id = f.get("subformId")
            if not sub_id:
                errors.append(f"فیلد «{key}»: زیرفرم انتخاب نشده است")
                continue
            if sub_id == (f.get("__formId__")):
                errors.append(f"فیلد «{key}»: ارجاع چرخه‌ای به خود فرم مجاز نیست")
                continue
            pub = db.scalar(select(FormVersion).where(
                FormVersion.form_id == sub_id, FormVersion.status == "published").order_by(FormVersion.version.desc()))
            if not pub:
                errors.append(f"فیلد «{key}»: زیرفرم انتخابی نسخه منتشرشده ندارد")
        if ftype == "calculated" and not f.get("formula"):
            errors.append(f"فیلد محاسباتی «{key}»: فرمول تعریف نشده است")
        if f.get("formula"):
            r = evaluate_formula(f["formula"], lambda k: 1)
            if r is None and f["formula"].strip():
                warnings.append(f"فرمول «{key}» با داده نمونه ارزیابی نشد؛ بررسی شود")
    # عمق ارجاع زیرفرم (حداکثر ۳ سطح)
    return errors, warnings


@router.get("/forms")
def list_forms(db: Session = Depends(get_db), user: User = Depends(get_current_user), q: str = ""):
    stmt = select(FormDefinition).order_by(FormDefinition.id.desc())
    if q:
        stmt = stmt.where(FormDefinition.title.contains(q))
    rows = db.scalars(stmt).all()
    return {"items": [form_out(f) for f in rows]}


@router.post("/forms")
def create_form(body: FormIn, db: Session = Depends(get_db), user: User = Depends(require_perm("form.manage")), request: Request = None):
    if db.scalar(select(FormDefinition).where(FormDefinition.key == body.key)):
        raise HTTPException(400, "کلید فرم تکراری است")
    f = FormDefinition(key=body.key, title=body.title, description=body.description, created_by_id=user.id)
    db.add(f)
    db.flush()
    v = FormVersion(form_id=f.id, version=1, schema_json={"title": body.title, "fields": []},
                    created_by_id=user.id, change_note="نسخه اولیه")
    db.add(v)
    db.commit()
    log_action(db, user.id, "form.created", "form", f.id, {"key": f.key}, request)
    return form_out(f)


@router.get("/forms/{fid}")
def get_form(fid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    f = db.get(FormDefinition, fid)
    if not f:
        raise HTTPException(404, "فرم یافت نشد")
    out = form_out(f)
    out["versions"] = [version_out(v) for v in f.versions]
    return out


@router.put("/forms/{fid}")
def update_form(fid: int, body: FormIn, db: Session = Depends(get_db), user: User = Depends(require_perm("form.manage")), request: Request = None):
    f = db.get(FormDefinition, fid)
    if not f:
        raise HTTPException(404, "فرم یافت نشد")
    f.title, f.description = body.title, body.description
    db.commit()
    log_action(db, user.id, "form.updated", "form", f.id, {}, request)
    return form_out(f)


@router.delete("/forms/{fid}")
def delete_form(fid: int, db: Session = Depends(get_db), user: User = Depends(require_perm("form.manage")), request: Request = None):
    f = db.get(FormDefinition, fid)
    if not f:
        raise HTTPException(404, "فرم یافت نشد")
    used = db.scalar(select(func.count()).select_from(FormSubmission).where(FormSubmission.form_version_id.in_(
        select(FormVersion.id).where(FormVersion.form_id == fid))))
    if used:
        raise HTTPException(400, "این فرم داده ثبت‌شده دارد و حذف آن مجاز نیست")
    db.delete(f)
    db.commit()
    log_action(db, user.id, "form.deleted", "form", fid, {}, request)
    return {"ok": True}


@router.get("/forms/versions/published-by-form/{fid}")
def published_version_by_form(fid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """واکشی آخرین نسخه منتشرشده یک فرم (برای زیرفرم‌ها و پیش‌نمایش)."""
    v = db.scalar(select(FormVersion).where(
        FormVersion.form_id == fid, FormVersion.status == "published").order_by(FormVersion.version.desc()))
    if not v:
        raise HTTPException(404, "این فرم نسخه منتشرشده ندارد")
    out = version_out(v, include_schema=True)
    out["form"] = {"id": v.form.id, "key": v.form.key, "title": v.form.title}
    return out


@router.get("/forms/versions/{vid}")
def get_version(vid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    v = db.get(FormVersion, vid)
    if not v:
        raise HTTPException(404, "نسخه یافت نشد")
    out = version_out(v, include_schema=True)
    out["form"] = {"id": v.form.id, "key": v.form.key, "title": v.form.title}
    return out


@router.post("/forms/{fid}/versions")
def create_version(fid: int, body: VersionIn, db: Session = Depends(get_db), user: User = Depends(require_perm("form.manage")), request: Request = None):
    """ایجاد نسخه پیش‌نویس جدید — تغییر نام نمایشی فیلد ارتباط داده‌های قبلی را قطع نمی‌کند
    (فیلد با نام فنی پایدار ذخیره می‌شود)."""
    f = db.get(FormDefinition, fid)
    if not f:
        raise HTTPException(404, "فرم یافت نشد")
    last = db.scalar(select(FormVersion).where(FormVersion.form_id == fid).order_by(FormVersion.version.desc()))
    v = FormVersion(form_id=fid, version=(last.version + 1) if last else 1,
                    schema_json=body.schema_json.model_dump(), created_by_id=user.id, change_note=body.change_note)
    db.add(v)
    db.commit()
    log_action(db, user.id, "form.version_created", "form", fid, {"version": v.version}, request)
    return version_out(v, include_schema=True)


@router.put("/forms/versions/{vid}")
def update_version(vid: int, body: VersionIn, db: Session = Depends(get_db), user: User = Depends(require_perm("form.manage"))):
    v = db.get(FormVersion, vid)
    if not v:
        raise HTTPException(404, "نسخه یافت نشد")
    if v.status != "draft":
        raise HTTPException(400, "فقط نسخه پیش‌نویس قابل ویرایش است؛ نسخه جدید بسازید")
    v.schema_json = body.schema_json.model_dump()
    v.change_note = body.change_note
    db.commit()
    return version_out(v, include_schema=True)


@router.post("/forms/versions/{vid}/validate-structure")
def validate_structure(vid: int, db: Session = Depends(get_db), user: User = Depends(require_perm("form.manage"))):
    v = db.get(FormVersion, vid)
    if not v:
        raise HTTPException(404, "نسخه یافت نشد")
    errors, warnings = validate_schema_structure(db, v.schema_json)
    return {"errors": errors, "warnings": warnings}


@router.post("/forms/versions/{vid}/publish")
def publish_version(vid: int, db: Session = Depends(get_db), user: User = Depends(require_perm("form.publish")), request: Request = None):
    v = db.get(FormVersion, vid)
    if not v:
        raise HTTPException(404, "نسخه یافت نشد")
    if v.status == "published":
        raise HTTPException(400, "این نسخه قبلاً منتشر شده است")
    errors, warnings = validate_schema_structure(db, v.schema_json)
    if errors:
        raise HTTPException(400, {"message": "انتخاب نسخه به‌دلیل خطای قطعی مجاز نیست", "errors": errors, "warnings": warnings})
    v.status = "published"
    v.published_at = utcnow()
    v.published_by_id = user.id
    db.commit()
    log_action(db, user.id, "form.published", "form_version", v.id, {"form": v.form_id, "version": v.version}, request)
    return {"ok": True, "warnings": warnings}


@router.post("/forms/{fid}/validate-data")
def validate_data(fid: int, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """اعتبارسنجی داده نمونه با آخرین نسخه منتشرشده (پیش‌نمایش فرم)."""
    partial = bool(body.get("__partial__"))
    pub = db.scalar(select(FormVersion).where(FormVersion.form_id == fid, FormVersion.status == "published").order_by(FormVersion.version.desc()))
    if not pub:
        raise HTTPException(400, "این فرم نسخه منتشرشده ندارد")
    r = validate_form_data(db, pub.schema_json, body.get("data") or {}, partial=partial)
    return {"errors": r.errors, "cleaned": r.cleaned}
