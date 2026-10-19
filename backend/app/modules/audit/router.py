# -*- coding: utf-8 -*-
"""API مشاهده سوابق ممیزی — فقط برای حسابرس و مدیر سامانه."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_perm
from app.modules.identity.models import User
from app.modules.audit.service import AuditLog

router = APIRouter()


@router.get("/audit")
def list_audit(page: int = 1, page_size: int = 50, action: str = "",
               db: Session = Depends(get_db), user: User = Depends(require_perm("audit.view"))):
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    if action:
        stmt = stmt.where(AuditLog.action.contains(action))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{
        "id": a.id, "user_id": a.user_id, "action": a.action, "entity": a.entity,
        "entity_id": a.entity_id, "detail": a.detail_json, "ip": a.ip,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a in rows], "total": total}
