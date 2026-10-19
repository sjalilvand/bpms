# -*- coding: utf-8 -*-
"""آزمون‌های فاز ۵ — API بیرونی: احراز کلید/امضا، idempotency، scopes، rate limit و Webhook."""
import hashlib
import hmac
import http.server
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.modules.external import service as ext
from app.modules.external.models import ExternalClient, ExternalIdempotency, WebhookDelivery, WebhookEndpoint


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture()
def client_factory(db):
    """ساخت کلید سرویس بیرونی برای هر آزمون."""
    created = []

    def _make(key_id="bpms_test", secret="test-secret-123", scopes=None,
              require_signature=False, rate=1000, actor="admin"):
        _make_admin(db)  # کاربر نماینده باید وجود داشته باشد
        # پاک‌سازی بقایای اجرای قبلی با همان کلید (پایگاه آزمون پایدار است)
        stale = db.scalar(select(ExternalClient).where(ExternalClient.key_id == key_id))
        if stale:
            for row in db.scalars(select(ExternalIdempotency).where(
                    ExternalIdempotency.client_id == stale.id)).all():
                db.delete(row)
            db.flush()  # حذف وابسته‌ها قبل از کلید اصلی (ترتیب حذف در UoW)
            db.delete(stale)
            db.commit()
        c = ExternalClient(name="تست", key_id=key_id, key_secret=secret,
                           scopes=scopes if scopes is not None else ["*"],
                           require_signature=require_signature, rate_limit_per_min=rate,
                           actor_username=actor)
        db.add(c)
        db.commit()
        created.append(c.id)
        return c

    yield _make
    try:
        for cid in created:
            for row in db.scalars(select(ExternalIdempotency).where(
                    ExternalIdempotency.client_id == cid)).all():
                db.delete(row)
            db.flush()
            c = db.get(ExternalClient, cid)
            if c:
                db.delete(c)
        db.commit()
    except Exception:
        db.rollback()
    ext._RATE_BUCKETS.clear()


@pytest.fixture()
def api():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def purchase_version(db):
    """تعریف مستقل آزمون: نسخه منتشرشده بدون فرم متصل — مستقل از داده seed."""
    from app.modules.engine.models import ProcessDefinition, ProcessVersion
    from app.core.database import Base, engine as _engine
    Base.metadata.create_all(bind=_engine)
    bpmn = open("data/bpmn/purchase_request.bpmn", encoding="utf-8").read()
    p = db.scalar(select(ProcessDefinition).where(ProcessDefinition.key == "purchase_request_ext_test"))
    if not p:
        p = ProcessDefinition(key="purchase_request_ext_test", title="درخواست خرید (آزمون فاز ۵)")
        db.add(p)
        db.flush()
    v = db.scalar(select(ProcessVersion).where(ProcessVersion.definition_id == p.id).order_by(
        ProcessVersion.version.desc()))
    if not v:
        v = ProcessVersion(definition_id=p.id, version=1, bpmn_xml=bpmn,
                           main_process_id="Process_PurchaseRequest",
                           config_json={"bindings": {}}, status="published")
        db.add(v)
        db.commit()
    return v


def _headers(key_id="bpms_test", secret=None, body=b"", sign=False, ts=None, **extra):
    h = {"X-API-Key": key_id}
    if sign and secret:
        t = ts or str(int(time.time()))
        h["X-Timestamp"] = t
        h["X-Signature"] = ext.compute_signature(secret, t, body)
    h.update(extra)
    return h


class TestExternalAuth:
    def test_missing_key_unauthorized(self, api, client_factory):
        r = api.get("/api/v1/external/v1/process-instances/999")
        assert r.status_code == 401

    def test_unknown_key_unauthorized(self, api, client_factory):
        r = api.get("/api/v1/external/v1/process-instances/999", headers=_headers("bpms_nothing"))
        assert r.status_code == 401

    def test_scope_enforced(self, api, client_factory):
        client_factory(key_id="bpms_reader", scopes=["instances.read"])
        r = api.post("/api/v1/external/v1/process-instances", json={"definition_key": "purchase_request"},
                     headers=_headers("bpms_reader"))
        assert r.status_code == 403

    def test_hmac_required_and_valid(self, api, client_factory, db, purchase_version):
        client_factory(key_id="bpms_hmac", require_signature=True)
        body = {"definition_key": "purchase_request_ext_test", "data": {}, "business_key": "EXT-HMAC-1"}
        # بدون امضا
        r = api.post("/api/v1/external/v1/process-instances", json=body, headers=_headers("bpms_hmac"))
        assert r.status_code == 401
        # امضای نادرست
        bad = {"X-API-Key": "bpms_hmac", "X-Timestamp": str(int(time.time())), "X-Signature": "0" * 64}
        r = api.post("/api/v1/external/v1/process-instances", json=body, headers=bad)
        assert r.status_code == 401
        # امضای درست — بایت‌های دقیقاً همان‌طور که httpx می‌فرستد (جداکننده فشرده)
        raw = json.dumps(body, separators=(",", ":")).encode()
        r = api.post("/api/v1/external/v1/process-instances", json=body,
                     headers=_headers("bpms_hmac", "test-secret-123", raw, sign=True))
        assert r.status_code == 200, r.text

    def test_stale_timestamp_rejected(self, api, client_factory):
        client_factory(key_id="bpms_hmac2", require_signature=True)
        old_ts = str(int(time.time()) - 4000)
        body = {"definition_key": "purchase_request", "data": {}}
        h = {"X-API-Key": "bpms_hmac2", "X-Timestamp": old_ts,
             "X-Signature": ext.compute_signature("test-secret-123", old_ts, json.dumps(body).encode())}
        r = api.post("/api/v1/external/v1/process-instances", json=body, headers=h)
        assert r.status_code == 401

    def test_rate_limit(self, api, client_factory):
        client_factory(key_id="bpms_limited", rate=2)
        for _ in range(2):
            r = api.get("/api/v1/external/v1/process-instances/999", headers=_headers("bpms_limited"))
            assert r.status_code == 404  # کلید معتبر، نمونه نیست
        r = api.get("/api/v1/external/v1/process-instances/999", headers=_headers("bpms_limited"))
        assert r.status_code == 429


class TestIdempotency:
    def _start_payload(self, bk):
        return {"definition_key": "purchase_request_ext_test", "data": {}, "business_key": bk}

    def test_replay_same_key_same_body(self, api, client_factory, db, purchase_version):
        client_factory()
        payload = self._start_payload("EXT-IDEM-1")
        r1 = api.post("/api/v1/external/v1/process-instances", json=payload,
                      headers=_headers(**{"Idempotency-Key": "IDEM-1"}))
        assert r1.status_code == 200
        r2 = api.post("/api/v1/external/v1/process-instances", json=payload,
                      headers=_headers(**{"Idempotency-Key": "IDEM-1"}))
        assert r2.status_code == 200
        assert r2.headers.get("X-Idempotent-Replay") == "true"
        assert r1.json()["id"] == r2.json()["id"]
        # فقط یک نمونه برای این کلید ساخته شده است (بقایای اجراهای قبلی نادیده)
        from app.modules.engine.models import ProcessInstance
        n = len(db.scalars(select(ProcessInstance).where(
            ProcessInstance.business_key == "EXT-IDEM-1",
            ProcessInstance.id == r1.json()["id"])).all())
        assert n == 1

    def test_conflict_same_key_different_body(self, api, client_factory, purchase_version):
        client_factory()
        r1 = api.post("/api/v1/external/v1/process-instances", json=self._start_payload("EXT-IDEM-2"),
                      headers=_headers(**{"Idempotency-Key": "IDEM-2"}))
        assert r1.status_code == 200
        r2 = api.post("/api/v1/external/v1/process-instances", json=self._start_payload("EXT-IDEM-3"),
                      headers=_headers(**{"Idempotency-Key": "IDEM-2"}))
        assert r2.status_code == 409

    def test_complete_with_idempotency(self, api, client_factory, db, purchase_version):
        client_factory()
        # شروع نمونه + تکمیل وظیفه ثبت دو بار با همان کلید
        r = api.post("/api/v1/external/v1/process-instances", json=self._start_payload("EXT-IDEM-4"),
                     headers=_headers(**{"Idempotency-Key": "IDEM-S4"}))
        iid = r.json()["id"]
        st = api.get(f"/api/v1/external/v1/process-instances/{iid}", headers=_headers()).json()
        task_id = st["open_tasks"][0]["id"]
        body = {"data": {}, "result": None, "comment": "تکمیل بیرونی"}
        h = _headers(**{"Idempotency-Key": "IDEM-C4"})
        c1 = api.post(f"/api/v1/external/v1/tasks/{task_id}/complete", json=body, headers=h)
        assert c1.status_code == 200, c1.text
        c2 = api.post(f"/api/v1/external/v1/tasks/{task_id}/complete", json=body, headers=h)
        assert c2.status_code == 200
        assert c2.headers.get("X-Idempotent-Replay") == "true"


class TestExternalStatus:
    def test_status_not_found(self, api, client_factory):
        client_factory()
        r = api.get("/api/v1/external/v1/process-instances/999999", headers=_headers())
        assert r.status_code == 404

    def test_start_via_definition_key_missing(self, api, client_factory):
        client_factory()
        r = api.post("/api/v1/external/v1/process-instances", json={"definition_key": "nope"},
                     headers=_headers())
        assert r.status_code == 404


class TestWebhook:
    def _local_receiver(self):
        """سرور HTTP محلی برای دریافت Webhook + بررسی امضا."""
        received = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                received.append({"headers": dict(self.headers), "body": body})
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok": true}')

            def log_message(self, *a):  # بی‌صدا
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        return server, f"http://127.0.0.1:{port}/hook", received

    def test_webhook_signed_delivery(self, api, client_factory, db, purchase_version):
        server, url, received = self._local_receiver()
        secret = "hook-secret-xyz"
        w = WebhookEndpoint(url=url, secret=secret, events=["instance.started"])
        db.add(w)
        db.commit()
        wid = w.id
        try:
            client_factory()
            r = api.post("/api/v1/external/v1/process-instances",
                         json=self_payload("EXT-WH-1"), headers=_headers())
            assert r.status_code == 200
            # انتظار تحویل در نخ پس‌زمینه
            deadline = time.time() + 15
            row = None
            while time.time() < deadline:
                row = db.scalar(select(WebhookDelivery).where(
                    WebhookDelivery.endpoint_id == w.id).order_by(WebhookDelivery.id.desc()))
                if row and row.status == "success":
                    break
                time.sleep(0.3)
                db.expire_all()
            assert row and row.status == "success", f"delivery status: {row and row.status}"
            assert received, "سرور مقصد چیزی دریافت نکرد"
            sig = received[0]["headers"].get("X-BPMS-Signature", "")
            ts = received[0]["headers"].get("X-BPMS-Timestamp", "")
            expect = "sha256=" + hmac.new(secret.encode(), f"{ts}.".encode() + received[0]["body"], hashlib.sha256).hexdigest()
            assert hmac.compare_digest(sig, expect), "امضای Webhook درست نیست"
        finally:
            server.shutdown()
            try:
                for row in db.scalars(select(WebhookDelivery).where(
                        WebhookDelivery.endpoint_id == wid)).all():
                    db.delete(row)
                db.flush()
                ep = db.get(WebhookEndpoint, wid)
                if ep:
                    db.delete(ep)
                db.commit()
            except Exception:
                db.rollback()

    def test_admin_crud_and_scope_validation(self, api, client_factory, db):
        # کاربر مدیر
        from app.modules.identity.models import User
        u = db.scalar(select(User).where(User.username == "admin")) or _make_admin(db)
        token = create_access_token(str(u.id), {"username": "admin"})
        h = {"Authorization": f"Bearer {token}"}
        # دامنه نامعتبر رد می‌شود
        r = api.post("/api/v1/integrations/clients", json={"name": "سرویس تست", "scopes": ["bogus"]}, headers=h)
        assert r.status_code == 400
        # ساخت موفق — secret یک‌بار برگردانده می‌شود
        r = api.post("/api/v1/integrations/clients", json={"name": "سرویس تست", "scopes": ["instances.read"]},
                     headers=h)
        assert r.status_code == 200 and r.json().get("key_secret")
        # فهرست بدون secret
        r = api.get("/api/v1/integrations/clients", headers=h)
        assert all("key_secret" not in c for c in r.json()["items"])
        # چرخش رمز
        kid = r.json()["items"][-1]["id"]
        r2 = api.post(f"/api/v1/integrations/clients/{kid}/rotate-secret", headers=h)
        assert r2.status_code == 200 and r2.json().get("key_secret")
        # webhook: URL نامعتبر (پس از اعتبارسنجی pydantic)
        r3 = api.post("/api/v1/integrations/webhooks", json={"url": "not-a-url-99"}, headers=h)
        assert r3.status_code == 400


# ---------------- ابزارهای آزمون ----------------
def self_payload(bk):
    return {"definition_key": "purchase_request_ext_test", "data": {}, "business_key": bk}


def _make_admin(db):
    from sqlalchemy.exc import IntegrityError
    from app.modules.identity.models import User
    from app.core.security import hash_password
    u = db.scalar(select(User).where(User.username == "admin"))
    if u:
        return u
    try:
        u = User(username="admin", password_hash=hash_password("Bpms@1234"),
                 full_name="مدیر", is_superadmin=True)
        db.add(u)
        db.commit()
        return u
    except IntegrityError:
        db.rollback()
        return db.scalar(select(User).where(User.username == "admin"))
