# -*- coding: utf-8 -*-
"""پیوست‌ها — ذخیره خارج از مسیر عمومی اجرایی + کنترل مجوز دانلود."""
import os
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.core.config import settings
from app.core.database import get_db, Base
from app.core.deps import get_current_user
from app.modules.identity.models import User, utcnow
from app.modules.audit.service import log_action

router = APIRouter()

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_\u0600-\u06FF\-.]")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_name: Mapped[str] = mapped_column(String(300))
    stored_name: Mapped[str] = mapped_column(String(120), unique=True)
    content_type: Mapped[str | None] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    instance_id: Mapped[int | None] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


MAX_MB = settings.MAX_UPLOAD_MB
BLOCKED_EXT = {".exe", ".bat", ".cmd", ".sh", ".ps1", ".js", ".vbs", ".msi"}


@router.post("/attachments")
async def upload(instance_id: int | None = None, file: UploadFile = File(...),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    raw = await file.read()
    if len(raw) > MAX_MB * 1024 * 1024:
        raise HTTPException(400, f"حجم فایل بیش از {MAX_MB} مگابایت است")
    orig = os.path.basename(file.filename or "file")
    _base, ext = os.path.splitext(orig)
    if ext.lower() in BLOCKED_EXT:
        raise HTTPException(400, "نوع فایل مجاز نیست")
    stored = f"{uuid.uuid4().hex}{ext.lower()[:10]}"
    path = os.path.join(settings.UPLOAD_DIR, stored)
    with open(path, "wb") as f:
        f.write(raw)
    a = Attachment(original_name=SAFE_NAME_RE.sub("_", orig)[:290], stored_name=stored,
                   content_type=file.content_type, size=len(raw), uploaded_by_id=user.id,
                   instance_id=instance_id)
    db.add(a)
    db.commit()
    log_action(db, user.id, "attachment.uploaded", "attachment", a.id, {"name": a.original_name})
    return {"id": a.id, "name": a.original_name, "size": a.size, "content_type": a.content_type}


@router.get("/attachments")
def list_attachments(instance_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from sqlalchemy import select
    stmt = select(Attachment).order_by(Attachment.id.desc()).limit(200)
    if instance_id:
        stmt = stmt.where(Attachment.instance_id == instance_id)
    rows = db.scalars(stmt).all()
    return {"items": [{"id": a.id, "name": a.original_name, "size": a.size,
                       "content_type": a.content_type, "instance_id": a.instance_id,
                       "uploaded_by_id": a.uploaded_by_id} for a in rows]}


@router.get("/attachments/{aid}/download")
def download(aid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = db.get(Attachment, aid)
    if not a:
        raise HTTPException(404, "پیوست یافت نشد")
    path = os.path.join(settings.UPLOAD_DIR, a.stored_name)
    if not os.path.exists(path):
        raise HTTPException(404, "فایل یافت نشد")
    return FileResponse(path, filename=a.original_name, media_type=a.content_type or "application/octet-stream")
