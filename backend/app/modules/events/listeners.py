# -*- coding: utf-8 -*-
"""صف رویداد زنده روی نشست SQLAlchemy — انتشار پس از commit موفق.

کاربرد: queue_event(db, [user_id], "notification", {...}) — پس از commit
شنونده after_commit رویداد را به گذرگاه (SSE) منتشر می‌کند. با rollback
رویدادها دور ریخته می‌شوند (هیچ اعلان کاذبی برای تراکنش ناموفق نمی‌رود).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import event

from app.modules.events.bus import bus

PENDING_KEY = "bpms_pending_events"


def queue_event(db: Session, user_ids, event_type: str, payload: dict | None = None) -> None:
    """ثبت رویداد برای انتشار پس از commit — بدون I/O در همین لحظه."""
    try:
        pending = db.info.setdefault(PENDING_KEY, [])
        pending.append({
            "type": event_type,
            "data": payload or {},
            "users": [int(u) for u in (user_ids or []) if u],
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass


def _drain(session: Session):
    try:
        return session.info.pop(PENDING_KEY, [])
    except Exception:
        return []


@event.listens_for(Session, "after_commit")
def _publish_after_commit(session: Session) -> None:
    for ev in _drain(session):
        bus.publish_threadsafe(ev["users"], {"type": ev["type"], "data": ev["data"], "ts": ev["ts"]})


@event.listens_for(Session, "after_soft_rollback")
def _clear_on_rollback(session: Session, transaction) -> None:  # pragma: no cover
    _drain(session)


@event.listens_for(Session, "after_rollback")
def _clear_after_rollback(session: Session) -> None:  # pragma: no cover
    _drain(session)
