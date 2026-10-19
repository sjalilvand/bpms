# -*- coding: utf-8 -*-
"""تست گذرگاه رویداد زنده و انتشار پس از commit (فاز ۳ — SSE)."""
import asyncio

import pytest

from app.modules.events.bus import EventBus
from app.modules.events.listeners import queue_event
from app.core.database import SessionLocal
from app.modules.identity.models import Role, User
from app.modules.notifications.service import Notification, notify_user, notify_role


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestEventBus:
    def test_subscribe_publish_receive(self):
        bus = EventBus()
        loop = asyncio.new_event_loop()
        try:
            bus.set_loop(loop)

            async def scenario():
                q = bus.subscribe(42)
                bus.publish_threadsafe([42], {"type": "notification", "data": {"title": "سلام"}})
                # انتشار از نخ دیگر هم باید کار کند (شبیه‌سازی کد همگام)
                ev = await asyncio.wait_for(q.get(), timeout=2)
                return ev

            ev = loop.run_until_complete(asyncio.wait_for(scenario(), timeout=5))
            assert ev["type"] == "notification"
            assert ev["data"]["title"] == "سلام"
        finally:
            loop.close()

    def test_filtering_by_user(self):
        bus = EventBus()
        loop = asyncio.new_event_loop()
        try:
            bus.set_loop(loop)

            async def scenario():
                q_a = bus.subscribe(1)
                q_b = bus.subscribe(2)
                bus.publish_threadsafe([2], {"type": "notification", "data": {}})
                got_a, got_b = "empty", "empty"
                try:
                    got_a = await asyncio.wait_for(q_a.get(), timeout=0.2)
                except asyncio.TimeoutError:
                    got_a = "timeout"
                got_b = await asyncio.wait_for(q_b.get(), timeout=1)
                return got_a, got_b

            got_a, got_b = loop.run_until_complete(asyncio.wait_for(scenario(), timeout=5))
            assert got_a == "timeout", "رویداد نباید به کاربر دیگر نشت کند"
            assert got_b["type"] == "notification"
        finally:
            loop.close()

    def test_unsubscribe_stops_delivery(self):
        bus = EventBus()
        loop = asyncio.new_event_loop()
        try:
            bus.set_loop(loop)

            async def scenario():
                q = bus.subscribe(7)
                bus.unsubscribe(7, q)
                bus.publish_threadsafe([7], {"type": "x", "data": {}})
                assert bus.subscriber_count(7) == 0

            loop.run_until_complete(asyncio.wait_for(scenario(), timeout=5))
        finally:
            loop.close()

    def test_multiple_subscribers_same_user(self):
        bus = EventBus()
        loop = asyncio.new_event_loop()
        try:
            bus.set_loop(loop)

            async def scenario():
                q1 = bus.subscribe(9)
                q2 = bus.subscribe(9)
                bus.publish_threadsafe([9], {"type": "x", "data": {"i": 1}})
                e1 = await asyncio.wait_for(q1.get(), timeout=1)
                e2 = await asyncio.wait_for(q2.get(), timeout=1)
                return e1, e2

            e1, e2 = loop.run_until_complete(asyncio.wait_for(scenario(), timeout=5))
            assert e1["data"] == {"i": 1} and e2["data"] == {"i": 1}
        finally:
            loop.close()


class TestAfterCommitPublishing:
    def test_notification_commit_publishes_event(self):
        """اعلان ثبت‌شده باید پس از commit به گذرگاه زنده منتشر شود."""
        from app.main import startup  # ثبت شنونده‌ها و مدل‌ها
        startup()
        bus = EventBus()
        loop = asyncio.new_event_loop()
        try:
            # شنونده after_commit از نمونه bus ماژول استفاده می‌کند — آن را جایگزین می‌کنیم
            import app.modules.events.listeners as listeners
            original = listeners.bus
            listeners.bus = bus
            bus.set_loop(loop)
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.is_active.is_(True)).first()
                q = bus.subscribe(user.id)
                notify_user(db, user.id, "اعلان آزمون SSE", "متن آزمون", link="/inbox")
                db.commit()
            finally:
                db.close()

            async def get_ev():
                return await asyncio.wait_for(q.get(), timeout=3)

            ev = loop.run_until_complete(asyncio.wait_for(get_ev(), timeout=6))
            assert ev["type"] == "notification"
            assert ev["data"]["title"] == "اعلان آزمون SSE"
        finally:
            listeners.bus = original
            loop.close()

    def test_rollback_discards_events(self):
        from app.main import startup
        startup()
        bus = EventBus()
        loop = asyncio.new_event_loop()
        try:
            import app.modules.events.listeners as listeners
            original = listeners.bus
            listeners.bus = bus
            bus.set_loop(loop)
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.is_active.is_(True)).first()
                q = bus.subscribe(user.id)
                notify_user(db, user.id, "نباید منتشر شود", "")
                db.rollback()
            finally:
                db.close()

            async def try_get():
                try:
                    return await asyncio.wait_for(q.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    return "timeout"

            assert loop.run_until_complete(asyncio.wait_for(try_get(), timeout=4)) == "timeout"
        finally:
            listeners.bus = original
            loop.close()
