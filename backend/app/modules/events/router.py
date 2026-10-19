# -*- coding: utf-8 -*-
"""جریان رویداد زنده (Server-Sent Events) — /events/stream.

- احراز هویت با توکن در پارامتر (EventSource امکان هدر ندارد).
- رویدادها به تفکیک کاربر فیلتر می‌شوند (فقط رویدادهای خود کاربر).
- رویداد hello در ابتدا + ping هر ۲۵ ثانیه برای نگه‌داشتن اتصال.
- پشتیبان‌گیری: اگر مرورگر EventSource نداشته باشد، رابط کاربری به نظرسنجی دوره‌ای
  اعلان‌ها بازمی‌گردد (رفتار پیشین حفظ شده است).
"""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.security import decode_access_token
from app.modules.identity.models import User
from app.modules.notifications.service import Notification
from app.modules.events.bus import bus

router = APIRouter()

KEEPALIVE_SECONDS = 25


def _auth_user(token: str, db: Session) -> User | None:
    payload = decode_access_token(token or "")
    if not payload or "sub" not in payload:
        return None
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        return None
    return user


@router.get("/events/stream")
async def stream(request: Request, token: str = ""):
    db = SessionLocal()
    try:
        user = _auth_user(token, db)
    finally:
        db.close()
    if user is None:
        raise HTTPException(401, "نشست نامعتبر است؛ دوباره وارد شوید")
    user_id = user.id

    unread = 0
    db = SessionLocal()
    try:
        unread = db.scalar(select(func.count()).select_from(Notification).where(
            Notification.user_id == user_id, Notification.is_read.is_(False))) or 0
    finally:
        db.close()

    queue = bus.subscribe(user_id)

    async def event_gen():
        try:
            hello = {"type": "hello", "data": {"user_id": user_id, "unread": unread}}
            yield f"event: hello\ndata: {json.dumps(hello, ensure_ascii=False)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                    data = json.dumps(ev.get("data") or {}, ensure_ascii=False, default=str)
                    yield f"event: {ev.get('type', 'message')}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            bus.unsubscribe(user_id, queue)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/events/health")
def events_health():
    return {"stream_clients": bus.subscriber_count(), "ok": True}
