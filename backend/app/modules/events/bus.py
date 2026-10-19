# -*- coding: utf-8 -*-
"""گذرگاه رویداد زنده (SSE) — انتشار درون‌فرایندی + پل اختیاری Redis.

طراحی:
- هر اتصال SSE یک asyncio.Queue اختصاصی دارد (به تفکیک user_id).
- انتشار از کد همگام (threadpool) با call_soon_threadsafe انجام می‌شود.
- اگر BPMS_REDIS_URL تنظیم شده باشد، رویدادها به کانال Redis منتشر و از آن
  دریافت می‌شوند تا در استقرار چندفرایندی (چند uvicorn worker / Celery) نیز
  اتصال‌های همه فرایندها رویداد را بگیرند. نبودِ Redis به‌صورت بازگشتی (fallback)
  مدیریت می‌شود و عملکرد درون‌فرایندی مختل نمی‌شود.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import uuid

logger = logging.getLogger("bpms.events")

INSTANCE_ID = uuid.uuid4().hex[:12]
CHANNEL = "bpms:events"


class EventBus:
    def __init__(self):
        self._subs: dict[int, set[asyncio.Queue]] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._redis = None
        self._redis_task: asyncio.Task | None = None
        self._redis_url = ""
        try:
            from app.core.config import settings
            self._redis_url = (settings.REDIS_URL or "").strip()
        except Exception:
            self._redis_url = (os.environ.get("BPMS_REDIS_URL", "") or "").strip()
        self._redis_enabled = bool(self._redis_url)

    # ---------- اتصال ----------
    def set_loop(self, loop: asyncio.AbstractEventLoop | None) -> None:
        self._loop = loop

    def subscribe(self, user_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        with self._lock:
            self._subs.setdefault(int(user_id), set()).add(q)
        return q

    def unsubscribe(self, user_id: int, q: asyncio.Queue) -> None:
        with self._lock:
            queues = self._subs.get(int(user_id))
            if queues:
                queues.discard(q)
                if not queues:
                    self._subs.pop(int(user_id), None)

    def subscriber_count(self, user_id: int | None = None) -> int:
        with self._lock:
            if user_id is None:
                return sum(len(s) for s in self._subs.values())
            return len(self._subs.get(int(user_id), ()))

    # ---------- انتشار ----------
    def publish_threadsafe(self, user_ids, event: dict) -> None:
        """انتشار از هر نخ (thread) — امن برای کد همگام SQLAlchemy."""
        payload = {**event, "_origin": INSTANCE_ID, "_ts": event.get("ts") or ""}
        users = [int(u) for u in (user_ids or []) if u]
        if not users:
            return
        self._publish_local(users, payload)
        self._publish_redis(users, payload)

    def _publish_local(self, users: list[int], payload: dict) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        with self._lock:
            targets = [q for uid in users for q in list(self._subs.get(uid, ()))]
        for q in targets:
            def _put(qq=q):
                try:
                    qq.put_nowait(payload)
                except asyncio.QueueFull:
                    pass
            try:
                loop.call_soon_threadsafe(_put)
            except RuntimeError:
                pass

    def _publish_redis(self, users: list[int], payload: dict) -> None:
        if not self._redis_enabled:
            return
        try:
            import redis as _redis
            r = _redis.Redis.from_url(self._redis_url, socket_connect_timeout=1,
                                      socket_timeout=1, decode_responses=True)
            msg = json.dumps({"users": users, "event": payload}, ensure_ascii=False, default=str)
            r.publish(CHANNEL, msg)
        except Exception:
            pass  # Redis اختیاری است؛ نبود آن نباید مسیر اصلی را بشکند

    # ---------- پل دریافت Redis (فرایند async سرور) ----------
    async def start_redis_bridge(self) -> None:
        if not self._redis_enabled or self._redis_task:
            return
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            self._redis_task = asyncio.create_task(self._redis_listener())
            logger.info("Redis event bridge enabled on channel %s", CHANNEL)
        except Exception as e:  # pragma: no cover
            logger.warning("Redis bridge disabled: %s", e)

    async def _redis_listener(self) -> None:  # pragma: no cover — نیازمند Redis
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(CHANNEL)
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                try:
                    data = json.loads(msg["data"])
                    if data.get("event", {}).get("_origin") == INSTANCE_ID:
                        continue  # رویداد خودمان را دوباره پخش نمی‌کنیم
                    self._publish_local(data.get("users") or [], data.get("event") or {})
                except Exception:
                    continue
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("redis listener stopped: %s", e)


bus = EventBus()
