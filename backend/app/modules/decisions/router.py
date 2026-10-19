# -*- coding: utf-8 -*-
"""API جدول تصمیم (DMN سبک) — تعریف، نسخه، اعتبارسنجی، انتشار و آزمون ارزیابی."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_perm
from app.modules.identity.models import User, utcnow
from app.modules.decisions import service as dsvc
from app.modules.decisions.models import DecisionDefinition, DecisionVersion
from app.modules.audit.service import log_action

router = APIRouter()


class DecisionIn(BaseModel):
    key: str
    title: str
    description: str = ""


class VersionIn(BaseModel):
    schema_json: dict
    change_note: str = ""


class EvaluateIn(BaseModel):
    data: dict


def version_out(v: DecisionVersion):
    return {
        "id": v.id, "definition_id": v.definition_id, "version": v.version,
        "schema_json": v.schema_json or {}, "status": v.status,
        "change_note": v.change_note,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "published_at": v.published_at.isoformat() if v.published_at else None,
    }


def definition_out(d: DecisionDefinition, include_versions: bool = False):
    out = {
        "id": d.id, "key": d.key, "title": d.title, "description": d.description,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "latest_published": version_out(d.latest_published) if d.latest_published else None,
    }
    if include_versions:
        out["versions"] = [version_out(v) for v in d.versions]
    return out


@router.get("/decisions")
def list_decisions(db: Session = Depends(get_db), user: User = Depends(get_current_user), q: str = ""):
    stmt = select(DecisionDefinition).order_by(DecisionDefinition.id.desc())
    if q:
        stmt = stmt.where(DecisionDefinition.title.contains(q))
    rows = db.scalars(stmt).all()
    return {"items": [definition_out(d) for d in rows]}


@router.post("/decisions")
def create_decision(body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(require_perm("decision.manage")), request: Request = None):
    if db.scalar(select(DecisionDefinition).where(DecisionDefinition.key == body.key)):
        raise HTTPException(400, "کلید جدول تصمیم تکراری است")
    d = DecisionDefinition(key=body.key, title=body.title, description=body.description, created_by_id=user.id)
    db.add(d)
    db.commit()
    log_action(db, user.id, "decision.created", "decision", d.id, {"key": d.key}, request)
    return {"id": d.id}


@router.get("/decisions/{did}")
def get_decision(did: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = db.get(DecisionDefinition, did)
    if not d:
        raise HTTPException(404, "جدول تصمیم یافت نشد")
    return definition_out(d, include_versions=True)


@router.put("/decisions/{did}")
def update_decision(did: int, body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(require_perm("decision.manage")), request: Request = None):
    d = db.get(DecisionDefinition, did)
    if not d:
        raise HTTPException(404, "جدول تصمیم یافت نشد")
    d.title, d.description = body.title, body.description
    db.commit()
    log_action(db, user.id, "decision.updated", "decision", d.id, {}, request)
    return {"ok": True}


@router.delete("/decisions/{did}")
def delete_decision(did: int, db: Session = Depends(get_db), user: User = Depends(require_perm("decision.manage")), request: Request = None):
    d = db.get(DecisionDefinition, did)
    if not d:
        raise HTTPException(404, "جدول تصمیم یافت نشد")
    db.delete(d)
    db.commit()
    log_action(db, user.id, "decision.deleted", "decision", did, {}, request)
    return {"ok": True}


@router.post("/decisions/{did}/versions")
def create_version(did: int, body: VersionIn, db: Session = Depends(get_db), user: User = Depends(require_perm("decision.manage")), request: Request = None):
    d = db.get(DecisionDefinition, did)
    if not d:
        raise HTTPException(404, "جدول تصمیم یافت نشد")
    errors = dsvc.validate_version_schema(body.schema_json)
    if errors:
        raise HTTPException(400, {"message": "جدول تصمیم نامعتبر است", "errors": [{"message": e} for e in errors]})
    last = db.scalar(select(DecisionVersion).where(DecisionVersion.definition_id == did)
                     .order_by(DecisionVersion.version.desc()))
    v = DecisionVersion(definition_id=did, version=(last.version + 1) if last else 1,
                        schema_json=body.schema_json, created_by_id=user.id, change_note=body.change_note)
    db.add(v)
    db.commit()
    log_action(db, user.id, "decision.version_created", "decision", did, {"version": v.version}, request)
    return version_out(v)


@router.get("/decisions/versions/{vid}")
def get_version(vid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    v = db.get(DecisionVersion, vid)
    if not v:
        raise HTTPException(404, "نسخه یافت نشد")
    out = version_out(v)
    out["definition"] = {"id": v.definition.id, "key": v.definition.key, "title": v.definition.title}
    return out


@router.put("/decisions/versions/{vid}")
def update_version(vid: int, body: VersionIn, db: Session = Depends(get_db), user: User = Depends(require_perm("decision.manage"))):
    v = db.get(DecisionVersion, vid)
    if not v:
        raise HTTPException(404, "نسخه یافت نشد")
    if v.status != "draft":
        raise HTTPException(400, "نسخه منتشرشده قابل ویرایش نیست؛ نسخه جدید بسازید")
    errors = dsvc.validate_version_schema(body.schema_json)
    if errors:
        raise HTTPException(400, {"message": "جدول تصمیم نامعتبر است", "errors": [{"message": e} for e in errors]})
    v.schema_json = body.schema_json
    v.change_note = body.change_note
    db.commit()
    return version_out(v)


@router.post("/decisions/versions/{vid}/validate")
def validate_version(vid: int, db: Session = Depends(get_db), user: User = Depends(require_perm("decision.manage"))):
    v = db.get(DecisionVersion, vid)
    if not v:
        raise HTTPException(404, "نسخه یافت نشد")
    return {"errors": dsvc.validate_version_schema(v.schema_json)}


@router.post("/decisions/versions/{vid}/publish")
def publish_version(vid: int, db: Session = Depends(get_db), user: User = Depends(require_perm("decision.manage")), request: Request = None):
    v = db.get(DecisionVersion, vid)
    if not v:
        raise HTTPException(404, "نسخه یافت نشد")
    if v.status == "published":
        raise HTTPException(400, "این نسخه قبلاً منتشر شده است")
    errors = dsvc.validate_version_schema(v.schema_json)
    if errors:
        raise HTTPException(400, {"message": "انتشار به‌دلیل خطای قطعی مجاز نیست", "errors": [{"message": e} for e in errors]})
    v.status = "published"
    v.published_at = utcnow()
    db.commit()
    log_action(db, user.id, "decision.published", "decision", v.definition_id, {"version": v.version}, request)
    return {"ok": True}


@router.post("/decisions/versions/{vid}/archive")
def archive_version(vid: int, db: Session = Depends(get_db), user: User = Depends(require_perm("decision.manage")), request: Request = None):
    """بایگانی نسخه منتشرشده — نسخه فعال را از مدار ارزیابی خارج می‌کند."""
    v = db.get(DecisionVersion, vid)
    if not v:
        raise HTTPException(404, "نسخه یافت نشد")
    if v.status != "published":
        raise HTTPException(400, "فقط نسخه منتشرشده قابل بایگانی است")
    v.status = "archived"
    v.active = False
    db.commit()
    log_action(db, user.id, "decision.archived", "decision", v.definition_id, {"version": v.version}, request)
    return {"ok": True}


@router.post("/decisions/{did}/evaluate")
def evaluate(did: int, body: EvaluateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """آزمون ارزیابی با داده ورودی — بر اساس نسخه منتشرشده."""
    d = db.get(DecisionDefinition, did)
    if not d:
        raise HTTPException(404, "جدول تصمیم یافت نشد")
    v = d.latest_published
    if not v:
        raise HTTPException(400, "جدول تصمیم نسخه منتشرشده ندارد")
    try:
        from app.modules.decisions.engine import DecisionTable, evaluate_table
        result = evaluate_table(DecisionTable.from_schema(v.schema_json), body.data or {})
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"result": result, "version": v.version}
