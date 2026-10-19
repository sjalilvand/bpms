# -*- coding: utf-8 -*-
"""API اعلان‌ها."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.identity.models import User
from app.modules.notifications.service import Notification

router = APIRouter()


@router.get("/notifications")
def list_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user), unread_only: bool = False):
    stmt = select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(100)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    rows = db.scalars(stmt).all()
    total = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.is_read.is_(False)))
    return {"items": [{
        "id": n.id, "title": n.title, "body": n.body, "link": n.link,
        "is_read": n.is_read, "created_at": n.created_at.isoformat() if n.created_at else None,
    } for n in rows], "unread": total}


@router.post("/notifications/{nid}/read")
def mark_read(nid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.get(Notification, nid)
    if n and n.user_id == user.id:
        n.is_read = True
        db.commit()
    return {"ok": True}


@router.post("/notifications/read-all")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    for n in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))).all():
        n.is_read = True
    db.commit()
    return {"ok": True}
