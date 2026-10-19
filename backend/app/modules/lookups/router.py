# -*- coding: utf-8 -*-
"""جداول پایه (Lookup): تعریف + آیتم‌های سلسله‌مراتبی + منبع داده کنترل‌ها."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, DateTime
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_perm
from app.modules.identity.models import User, utcnow

router = APIRouter()

try:
    from sqlalchemy import JSON as SAJSON
except Exception:  # pragma: no cover
    SAJSON = None

from sqlalchemy import String, ForeignKey, Boolean, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LookupDefinition(Base):
    __tablename__ = "lookup_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    items: Mapped[list["LookupItem"]] = relationship(back_populates="lookup", lazy="selectin", cascade="all, delete-orphan")


class LookupItem(Base):
    __tablename__ = "lookup_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    lookup_id: Mapped[int] = mapped_column(ForeignKey("lookup_definitions.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("lookup_items.id", ondelete="CASCADE"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    extra_json: Mapped[dict | None] = mapped_column(SAJSON, nullable=True) if SAJSON else mapped_column(Text, nullable=True)

    lookup: Mapped[LookupDefinition] = relationship(back_populates="items")


class LookupDefIn(BaseModel):
    key: str
    title: str
    description: str = ""


class LookupItemIn(BaseModel):
    code: str
    title: str
    parent_id: int | None = None
    sort_order: int = 0
    is_active: bool = True
    extra: dict | None = None


def item_tree(items: list[LookupItem], parent_id=None):
    return [{
        "id": i.id, "code": i.code, "title": i.title, "parent_id": i.parent_id,
        "sort_order": i.sort_order, "is_active": i.is_active, "extra": i.extra_json,
        "children": item_tree(items, i.id),
    } for i in sorted([x for x in items if x.parent_id == parent_id], key=lambda x: (x.sort_order, x.id))]


@router.get("/lookups")
def list_lookups(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(LookupDefinition).order_by(LookupDefinition.title)).all()
    return {"items": [{"id": r.id, "key": r.key, "title": r.title, "description": r.description} for r in rows]}


@router.post("/lookups")
def create_lookup(body: LookupDefIn, db: Session = Depends(get_db), user: User = Depends(require_perm("lookup.manage"))):
    if db.scalar(select(LookupDefinition).where(LookupDefinition.key == body.key)):
        raise HTTPException(400, "کلید تکراری است")
    r = LookupDefinition(key=body.key, title=body.title, description=body.description)
    db.add(r)
    db.commit()
    return {"id": r.id}


@router.delete("/lookups/{lid}")
def delete_lookup(lid: int, db: Session = Depends(get_db), user: User = Depends(require_perm("lookup.manage"))):
    r = db.get(LookupDefinition, lid)
    if not r:
        raise HTTPException(404, "یافت نشد")
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.get("/lookups/{lid}/items")
def get_items(lid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user),
              include_inactive: bool = True):
    rows = db.scalars(select(LookupItem).where(LookupItem.lookup_id == lid)).all()
    return {"items": item_tree(rows)}


@router.post("/lookups/{lid}/items")
def add_item(lid: int, body: LookupItemIn, db: Session = Depends(get_db), user: User = Depends(require_perm("lookup.manage"))):
    if not db.get(LookupDefinition, lid):
        raise HTTPException(404, "تعریف جدول پایه یافت نشد")
    it = LookupItem(lookup_id=lid, code=body.code, title=body.title, parent_id=body.parent_id,
                    sort_order=body.sort_order, is_active=body.is_active, extra_json=body.extra)
    db.add(it)
    db.commit()
    return {"id": it.id}


@router.put("/lookups/items/{item_id}")
def update_item(item_id: int, body: LookupItemIn, db: Session = Depends(get_db), user: User = Depends(require_perm("lookup.manage"))):
    it = db.get(LookupItem, item_id)
    if not it:
        raise HTTPException(404, "آیتم یافت نشد")
    if body.parent_id == item_id:
        raise HTTPException(400, "والد نمی‌تواند خود آیتم باشد")
    it.code, it.title, it.parent_id, it.sort_order, it.is_active = body.code, body.title, body.parent_id, body.sort_order, body.is_active
    it.extra_json = body.extra
    db.commit()
    return {"id": it.id}


@router.delete("/lookups/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db), user: User = Depends(require_perm("lookup.manage"))):
    """حذف داده استفاده‌شده محدود است — در این نسخه حذف نرم با غیرفعال‌سازی توصیه می‌شود."""
    it = db.get(LookupItem, item_id)
    if not it:
        raise HTTPException(404, "آیتم یافت نشد")
    children = db.scalars(select(LookupItem).where(LookupItem.parent_id == item_id)).all()
    if children:
        raise HTTPException(400, "ابتدا زیرمجموعه‌ها را حذف یا غیرفعال کنید")
    db.delete(it)
    db.commit()
    return {"ok": True}


def validate_lookup_value(db: Session, lookup_id: int, value) -> bool:
    """گزینه انتخابی سمت سرور بررسی می‌شود (قاعده یکپارچگی سند)."""
    if value in (None, ""):
        return True
    it = db.get(LookupItem, int(value))
    return bool(it and it.lookup_id == lookup_id)
