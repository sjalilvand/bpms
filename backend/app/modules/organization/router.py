# -*- coding: utf-8 -*-
"""APIهای ساختار سازمانی و جانشینی."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_perm
from app.modules.identity.models import User
from app.modules.organization.models import OrganizationUnit, Delegation

router = APIRouter()


class UnitIn(BaseModel):
    name: str
    code: str | None = None
    parent_id: int | None = None
    description: str = ""


@router.get("/org-units")
def list_units(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    roots = db.scalars(select(OrganizationUnit).where(OrganizationUnit.parent_id.is_(None))).all()
    return {"items": [r.to_tree() for r in roots]}


@router.post("/org-units")
def create_unit(body: UnitIn, db: Session = Depends(get_db), user: User = Depends(require_perm("org.manage"))):
    u = OrganizationUnit(name=body.name, code=body.code, parent_id=body.parent_id, description=body.description)
    db.add(u)
    db.commit()
    return {"id": u.id}


@router.put("/org-units/{uid}")
def update_unit(uid: int, body: UnitIn, db: Session = Depends(get_db), user: User = Depends(require_perm("org.manage"))):
    u = db.get(OrganizationUnit, uid)
    if not u:
        raise HTTPException(404, "واحد سازمانی یافت نشد")
    if body.parent_id == uid:
        raise HTTPException(400, "والد نمی‌تواند خود واحد باشد")
    u.name, u.code, u.parent_id, u.description = body.name, body.code, body.parent_id, body.description
    db.commit()
    return {"id": u.id}


@router.delete("/org-units/{uid}")
def delete_unit(uid: int, db: Session = Depends(get_db), user: User = Depends(require_perm("org.manage"))):
    u = db.get(OrganizationUnit, uid)
    if not u:
        raise HTTPException(404, "یافت نشد")
    if u.children:
        raise HTTPException(400, "ابتدا واحدهای زیرمجموعه را حذف کنید")
    users = db.scalars(select(User).where(User.org_unit_id == uid)).all()
    if users:
        raise HTTPException(400, "به این واحد کاربر تخصیص داده شده است")
    db.delete(u)
    db.commit()
    return {"ok": True}


# ---------- جانشینی ----------
class DelegationIn(BaseModel):
    from_user_id: int
    to_user_id: int
    start_date: date
    end_date: date
    note: str = ""


@router.get("/delegations")
def list_delegations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(Delegation).order_by(Delegation.id.desc())).all()
    return {"items": [{
        "id": d.id, "from_user_id": d.from_user_id, "to_user_id": d.to_user_id,
        "start_date": str(d.start_date), "end_date": str(d.end_date),
        "is_active": d.is_active, "note": d.note,
    } for d in rows]}


@router.post("/delegations")
def create_delegation(body: DelegationIn, db: Session = Depends(get_db), user: User = Depends(require_perm("org.manage"))):
    if body.from_user_id == body.to_user_id:
        raise HTTPException(400, "جانشین نمی‌تواند خود شخص باشد")
    d = Delegation(from_user_id=body.from_user_id, to_user_id=body.to_user_id,
                   start_date=body.start_date, end_date=body.end_date, note=body.note)
    db.add(d)
    db.commit()
    return {"id": d.id}


def active_delegators(db: Session, user_id: int) -> list[int]:
    """کاربرانی که در بازه جاری به این کاربر جانشینی داده‌اند."""
    today = date.today()
    rows = db.scalars(select(Delegation).where(
        Delegation.to_user_id == user_id, Delegation.is_active.is_(True),
        and_(Delegation.start_date <= today, Delegation.end_date >= today))).all()
    return [d.from_user_id for d in rows]
