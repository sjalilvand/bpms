# -*- coding: utf-8 -*-
"""آزمون‌های فاز ۶ — صف توزیع‌شده Webhook با Celery.

- ارسال تک‌تلاشی (_deliver_single) با امضای HMAC روی سرور محلی
- شکست موقت → TransientDeliveryFailure و ماندن وضعیت pending
- اتمام سهم تلاش → failed
- sweeper: بازیابی ردیف‌های pending یتیم و رد کردن سهم اتمام‌شده
- مسیریابی after_commit به صف Celery در SCHEDULER_MODE=celery
"""
import hashlib
import hmac
import http.server
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.main import app
from app.modules.external import webhooks
from app.modules.external.models import WebhookDelivery, WebhookEndpoint


class _Receiver:
    """سرور HTTP محلی برای دریافت Webhook + بررسی امضا."""

    def __init__(self, status=200):
        self.received = []
        self.status = status

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                self.parent_ref.received.append({"headers": dict(self.headers), "body": body})
                self.send_response(self.parent_ref.status)
                self.end_headers()
                self.wfile.write(b'{"ok": true}')

            def log_message(self, *a):  # بی‌صدا
                pass

        Handler.parent_ref = self
        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/hook"
        t = threading.Thread(target=self.server.serve_forever, daemon=True)
        t.start()

    def shutdown(self):
        self.server.shutdown()


@pytest.fixture()
def receiver():
    r = _Receiver()
    yield r
    r.shutdown()


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _make_endpoint(db, url, secret="wh-sec-123"):
    ep = WebhookEndpoint(url=url, secret=secret, events=["*"])
    db.add(ep)
    db.commit()
    return ep


def _cleanup(db, endpoint_id):
    for row in db.scalars(select(WebhookDelivery).where(
            WebhookDelivery.endpoint_id == endpoint_id)).all():
        db.delete(row)
    db.flush()
    ep = db.get(WebhookEndpoint, endpoint_id)
    if ep:
        db.delete(ep)
    db.commit()


class TestDeliverSingle:
    def test_success_with_signature(self, db, receiver):
        ep = _make_endpoint(db, receiver.url, secret="sig-check-1")
        try:
            d = WebhookDelivery(endpoint_id=ep.id, event_type="instance.completed",
                                payload_json={"id": 42}, status="pending")
            db.add(d)
            db.commit()
            did = d.id
            db.expire_all()
            out = webhooks._deliver_single(did)
            assert out.get("ok") is True and out.get("skipped") is None
            row = db.get(WebhookDelivery, did)
            db.expire_all()
            row = db.get(WebhookDelivery, did)
            assert row.status == "success" and row.attempts == 1
            assert row.delivered_at is not None
            assert receiver.received, "سرور مقصد چیزی دریافت نکرد"
            sig = receiver.received[0]["headers"].get("X-BPMS-Signature", "")
            ts = receiver.received[0]["headers"].get("X-BPMS-Timestamp", "")
            expect = "sha256=" + hmac.new(b"sig-check-1", f"{ts}.".encode() + receiver.received[0]["body"],
                                          hashlib.sha256).hexdigest()
            assert hmac.compare_digest(sig, expect)
        finally:
            _cleanup(db, ep.id)

    def test_transient_failure_keeps_pending_and_raises(self, db):
        # پورت بسته → خطای اتصال
        dead = _Receiver()
        dead_port = dead.port
        dead.shutdown()
        ep = _make_endpoint(db, f"http://127.0.0.1:{dead_port}/hook")
        try:
            d = WebhookDelivery(endpoint_id=ep.id, event_type="task.created",
                                payload_json={}, status="pending")
            db.add(d)
            db.commit()
            did = d.id
            with pytest.raises(webhooks.TransientDeliveryFailure):
                webhooks._deliver_single(did)
            db.expire_all()
            row = db.get(WebhookDelivery, did)
            assert row.status == "pending" and row.attempts == 1
            assert row.last_error
        finally:
            _cleanup(db, ep.id)

    def test_recovery_after_transient_failure(self, db, receiver):
        ep = _make_endpoint(db, receiver.url)
        try:
            d = WebhookDelivery(endpoint_id=ep.id, event_type="instance.started",
                                payload_json={}, status="pending", attempts=1,
                                last_error="شکست قبلی")
            db.add(d)
            db.commit()
            did = d.id
            out = webhooks._deliver_single(did)
            assert out.get("ok") is True
            db.expire_all()
            row = db.get(WebhookDelivery, did)
            assert row.status == "success" and row.attempts == 2
        finally:
            _cleanup(db, ep.id)

    def test_exhausted_attempts_marks_failed(self, db):
        dead = _Receiver()
        dead_port = dead.port
        dead.shutdown()
        ep = _make_endpoint(db, f"http://127.0.0.1:{dead_port}/hook")
        try:
            d = WebhookDelivery(endpoint_id=ep.id, event_type="task.completed",
                                payload_json={}, status="pending",
                                attempts=webhooks.WEBHOOK_MAX_ATTEMPTS - 1)
            db.add(d)
            db.commit()
            did = d.id
            out = webhooks._deliver_single(did)  # بدون raise — سهم اتمام یافته
            assert out.get("ok") is False and out.get("exhausted") is True
            db.expire_all()
            row = db.get(WebhookDelivery, did)
            assert row.status == "failed"
            assert row.attempts == webhooks.WEBHOOK_MAX_ATTEMPTS
        finally:
            _cleanup(db, ep.id)

    def test_skip_already_success(self, db, receiver):
        ep = _make_endpoint(db, receiver.url)
        try:
            d = WebhookDelivery(endpoint_id=ep.id, event_type="instance.cancelled",
                                payload_json={}, status="success", attempts=1)
            db.add(d)
            db.commit()
            did = d.id
            out = webhooks._deliver_single(did)
            assert out.get("ok") is True and out.get("skipped") is True
            time.sleep(0.2)
            assert not receiver.received, "برای ردیف موفق درخواست تکراری رفت"
        finally:
            _cleanup(db, ep.id)

    def test_gone_row(self, db):
        assert webhooks._deliver_single(999999) == {"ok": False, "gone": True}


class TestSweep:
    def test_sweep_redispatch_and_fail(self, db, monkeypatch):
        ep = _make_endpoint(db, "http://127.0.0.1:1/hook")
        try:
            old_ts = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=30)
            stale_ok = WebhookDelivery(endpoint_id=ep.id, event_type="e1", status="pending",
                                       attempts=0, created_at=old_ts)
            stale_exhausted = WebhookDelivery(endpoint_id=ep.id, event_type="e2", status="pending",
                                              attempts=webhooks.WEBHOOK_MAX_ATTEMPTS, created_at=old_ts)
            fresh = WebhookDelivery(endpoint_id=ep.id, event_type="e3", status="pending", attempts=0)
            db.add_all([stale_ok, stale_exhausted, fresh])
            db.commit()
            ids = {"stale_ok": stale_ok.id, "stale_exhausted": stale_exhausted.id, "fresh": fresh.id}

            sent = []

            class FakeCelery:
                def send_task(self, name, args=None, **kw):
                    sent.append((name, args))

            monkeypatch.setattr("app.worker.celery_app.celery_app", FakeCelery())
            out = webhooks.sweep_stale_deliveries(stale_minutes=10)
            assert out["redispatched"] == 1
            assert out["marked_failed"] == 1
            assert sent and sent[0][0] == "bpms.webhooks.deliver" and sent[0][1] == [ids["stale_ok"]]
            db.expire_all()
            assert db.get(WebhookDelivery, ids["stale_ok"]).status == "pending"
            assert db.get(WebhookDelivery, ids["stale_exhausted"]).status == "failed"
            assert db.get(WebhookDelivery, ids["fresh"]).status == "pending"
        finally:
            _cleanup(db, ep.id)


class TestCeleryRouting:
    def test_after_commit_routes_to_celery(self, db, monkeypatch):
        ep = _make_endpoint(db, "http://127.0.0.1:1/hook")
        try:
            monkeypatch.setattr(webhooks.settings, "SCHEDULER_MODE", "celery")
            sent = []

            class FakeCelery:
                def send_task(self, name, args=None, **kw):
                    sent.append((name, args))

            monkeypatch.setattr("app.worker.celery_app.celery_app", FakeCelery())
            webhooks.queue_webhook(db, "instance.started", {"instance_id": 7})
            db.commit()  # after_commit → صف Celery
            assert len(sent) == 1
            assert sent[0][0] == "bpms.webhooks.deliver"
            delivery_id = sent[0][1][0]
            row = db.get(WebhookDelivery, delivery_id)
            assert row is not None and row.status == "pending"
            assert row.event_type == "instance.started"
        finally:
            _cleanup(db, ep.id)
            webhooks._drain(db)

    def test_inprocess_mode_falls_back_to_thread(self, db, monkeypatch):
        monkeypatch.setattr(webhooks.settings, "SCHEDULER_MODE", "inprocess")
        called = {"send": 0}

        class FakeCelery:
            def send_task(self, *a, **k):
                called["send"] += 1

        monkeypatch.setattr("app.worker.celery_app.celery_app", FakeCelery())
        assert webhooks._dispatch_via_celery({"type": "x", "data": {}, "ts": "t"}) is False
        assert called["send"] == 0

    def test_broker_failure_returns_false(self, db, monkeypatch):
        ep = _make_endpoint(db, "http://127.0.0.1:1/hook")
        try:
            monkeypatch.setattr(webhooks.settings, "SCHEDULER_MODE", "celery")

            class BrokenCelery:
                def send_task(self, *a, **k):
                    raise ConnectionError("broker down")

            monkeypatch.setattr("app.worker.celery_app.celery_app", BrokenCelery())
            assert webhooks._dispatch_via_celery(
                {"type": "instance.started", "data": {}, "ts": "t"}) is False
        finally:
            _cleanup(db, ep.id)


class TestCeleryTasksRegistered:
    def test_tasks_registered(self):
        from app.worker.celery_app import celery_app
        assert celery_app is not None
        names = set(celery_app.tasks.keys())
        assert "bpms.webhooks.deliver" in names
        assert "bpms.webhooks.sweep" in names
        assert "bpms.engine.tick" in names
        assert "bpms.tasks.sla_check" in names

    def test_sweep_in_beat_schedule(self):
        from app.worker.celery_app import celery_app
        entries = celery_app.conf.beat_schedule
        assert any(e["task"] == "bpms.webhooks.sweep" for e in entries.values())
