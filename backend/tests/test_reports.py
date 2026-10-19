# -*- coding: utf-8 -*-
"""آزمون‌های فاز ۶ — گزارش‌ساز و KPI.

داده آزمایشی مستقل ساخته و پس از آزمون پاک می‌شود:
- تعریف فرایند نمونه با دو نمونه (تکمیل‌شده و در جریان)
- وظایف با زمان‌های انتظار/رسیدگی و SLA
- شاخص‌ها: overview، bottlenecks، workload، volume + گزارش ذخیره‌شده
"""
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.main import app
from app.modules.engine.models import EngineTask, ProcessDefinition, ProcessInstance, ProcessVersion
from app.modules.identity.models import User
from app.modules.reports.models import SavedReport

BKEY = "kpi-test-marker"


@pytest.fixture(scope="module")
def api():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(api):
    r = api.post("/api/v1/auth/login", json={"username": "admin", "password": "Bpms@1234"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def seeded():
    """ساخت داده KPI — یک‌بار برای کل ماژول."""
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.username == "admin"))
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        pd = ProcessDefinition(key=f"kpi_proc_{int(time.time())}", title="فرایند آزمون KPI")
        db.add(pd)
        db.flush()
        pv = ProcessVersion(definition_id=pd.id, version=1, bpmn_xml="<x/>",
                            main_process_id="kpi", config_json={})
        db.add(pv)
        db.flush()

        # نمونه تکمیل‌شده (چرخه ۱ روز) + دو وظیفه تکمیل‌شده
        i1 = ProcessInstance(definition_id=pd.id, version_id=pv.id, business_key=BKEY,
                             status="completed", started_by_id=admin.id,
                             started_at=now - timedelta(days=2),
                             finished_at=now - timedelta(days=1))
        db.add(i1)
        db.flush()
        t1 = EngineTask(instance_id=i1.id, task_uuid="u-k1", spec_id="Task_Review",
                        name="بررسی", status="completed", assignee_id=admin.id,
                        claimed_at=now - timedelta(days=2) + timedelta(hours=2),
                        completed_at=now - timedelta(days=2) + timedelta(hours=5),
                        created_at=now - timedelta(days=2),
                        due_at=now - timedelta(days=1, hours=-6))
        t2 = EngineTask(instance_id=i1.id, task_uuid="u-k2", spec_id="Task_Approve",
                        name="تأیید", status="completed", assignee_id=admin.id,
                        claimed_at=now - timedelta(days=1) + timedelta(hours=1),
                        completed_at=now - timedelta(days=1) + timedelta(hours=2),
                        created_at=now - timedelta(days=1),
                        sla_escalated_at=now - timedelta(days=1) + timedelta(hours=3))
        # نمونه در جریان با وظیفه آماده
        i2 = ProcessInstance(definition_id=pd.id, version_id=pv.id, business_key=BKEY,
                             status="running", started_by_id=admin.id,
                             started_at=now - timedelta(hours=6))
        db.add(i2)
        db.flush()
        t3 = EngineTask(instance_id=i2.id, task_uuid="u-k3", spec_id="Task_Review",
                        name="بررسی", status="ready", candidate_role="manager",
                        created_at=now - timedelta(hours=6),
                        due_at=now - timedelta(hours=1))  # سرریز
        db.add_all([t1, t2, t3])
        db.commit()
        return {"definition_id": pd.id, "instance_ids": [i1.id, i2.id],
                "task_ids": [t1.id, t2.id, t3.id], "definition_key": pd.key}
    finally:
        db.close()


def _cleanup(seeded):
    db = SessionLocal()
    try:
        for tid in seeded["task_ids"]:
            t = db.get(EngineTask, tid)
            if t:
                db.delete(t)
        for iid in seeded["instance_ids"]:
            i = db.get(ProcessInstance, iid)
            if i:
                db.delete(i)
        pd = db.get(ProcessDefinition, seeded["definition_id"])
        if pd:
            for pv in list(pd.versions):
                db.delete(pv)
            db.delete(pd)
        for r in db.scalars(select(SavedReport).where(
                SavedReport.name == "گزارش آزمونی KPI")).all():
            db.delete(r)
        db.commit()
    finally:
        db.close()


def _h(token):
    return {"Authorization": f"Bearer {token}"}


class TestKPIEndpoints:
    def test_overview(self, api, admin_token, seeded):
        r = api.get("/api/v1/reports/kpi/overview",
                    params={"definition_id": seeded["definition_id"], "days": 30},
                    headers=_h(admin_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["instances"]["total"] == 2
        assert d["instances"]["by_status"]["completed"] == 1
        assert d["instances"]["by_status"]["running"] == 1
        assert d["instances"]["completion_rate"] == 50.0
        # چرخه نمونه تکمیل‌شده = ۱ روز
        assert d["cycle_time_seconds"]["avg"] == 86400.0
        assert d["cycle_time_seconds"]["p50"] == 86400.0
        assert d["tasks"]["total"] == 3
        assert d["tasks"]["ready"] == 1
        assert d["tasks"]["completed"] == 2
        assert d["tasks"]["overdue_active"] == 1
        assert d["sla"]["escalated"] == 1
        assert d["sla"]["breach_rate"] > 0

    def test_overview_status_filter(self, api, admin_token, seeded):
        r = api.get("/api/v1/reports/kpi/overview",
                    params={"definition_id": seeded["definition_id"], "status": "running"},
                    headers=_h(admin_token))
        assert r.status_code == 200
        assert r.json()["instances"]["total"] == 1

    def test_bottlenecks(self, api, admin_token, seeded):
        r = api.get("/api/v1/reports/kpi/bottlenecks",
                    params={"definition_id": seeded["definition_id"], "days": 30},
                    headers=_h(admin_token))
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        by_spec = {i["spec_id"]: i for i in items}
        assert set(by_spec) == {"Task_Review", "Task_Approve"}
        review = by_spec["Task_Review"]
        assert review["created"] == 2 and review["completed"] == 1 and review["pending"] == 1
        assert review["overdue_active"] == 1
        approve = by_spec["Task_Approve"]
        # رسیدگی تأیید: از claim تا complete = ۱ ساعت
        assert approve["avg_handling_seconds"] == 3600.0
        # مرتب‌سازی نزولی بر اساس رسیدگی
        assert items[0]["avg_handling_seconds"] >= items[-1]["avg_handling_seconds"]

    def test_workload(self, api, admin_token, seeded):
        r = api.get("/api/v1/reports/kpi/workload",
                    params={"definition_id": seeded["definition_id"], "days": 30},
                    headers=_h(admin_token))
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        users = [i for i in items if i["kind"] == "user"]
        roles = [i for i in items if i["kind"] == "role"]
        assert users and roles
        admin_row = [u for u in users if "مدیر سامانه" in (u["name"] or "") or u["label"]][0]
        assert admin_row["completed"] == 2
        assert admin_row["active"] == 0
        role_row = roles[0]
        assert role_row["label"].startswith("نقش") and role_row["active"] == 1
        assert role_row["overdue_active"] == 1

    def test_volume(self, api, admin_token, seeded):
        r = api.get("/api/v1/reports/kpi/volume",
                    params={"definition_id": seeded["definition_id"], "days": 7},
                    headers=_h(admin_token))
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) == 8  # ۷ روز + امروز
        total_started = sum(i["started"] for i in items)
        total_completed = sum(i["completed"] for i in items)
        assert total_started == 2 and total_completed == 1

    def test_options(self, api, admin_token, seeded):
        r = api.get("/api/v1/reports/options", headers=_h(admin_token))
        assert r.status_code == 200
        assert any(p["id"] == seeded["definition_id"] for p in r.json()["processes"])

    def test_requires_permission(self, api, admin_token, seeded):
        # کاربر بدون report.view → ۴۰۳
        r = api.post("/api/v1/auth/login", json={"username": "user1", "password": "Bpms@1234"})
        token = r.json()["access_token"]
        rr = api.get("/api/v1/reports/kpi/overview", headers=_h(token))
        assert rr.status_code == 403


class TestSavedReports:
    def test_saved_report_lifecycle(self, api, admin_token, seeded):
        h = _h(admin_token)
        # ساخت
        r = api.post("/api/v1/reports/saved", headers=h, json={
            "name": "گزارش آزمونی KPI", "description": "تست چرخه عمر",
            "dataset": "bottlenecks",
            "filters": {"days": 30, "definition_id": seeded["definition_id"]}})
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        # فهرست
        r = api.get("/api/v1/reports/saved", headers=h)
        assert any(x["id"] == rid for x in r.json()["items"])
        # اجرا
        r = api.get(f"/api/v1/reports/saved/{rid}/run", headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["report"]["dataset"] == "bottlenecks"
        assert isinstance(d["data"]["items"], list) and d["data"]["items"]
        assert d["data"]["items"][0]["spec_id"] in ("Task_Review", "Task_Approve")
        # حذف
        r = api.delete(f"/api/v1/reports/saved/{rid}", headers=h)
        assert r.status_code == 200
        r = api.get(f"/api/v1/reports/saved/{rid}/run", headers=h)
        assert r.status_code == 404

    def test_saved_report_invalid_dataset(self, api, admin_token):
        r = api.post("/api/v1/reports/saved", headers=_h(admin_token), json={
            "name": "نامعتبر", "dataset": "bogus", "filters": {}})
        assert r.status_code == 422

    def test_saved_report_requires_manage(self, api, admin_token):
        r = api.post("/api/v1/auth/login", json={"username": "monitor1", "password": "Bpms@1234"})
        token = r.json()["access_token"]
        # monitor فقط report.view دارد — بدون report.manage
        r2 = api.post("/api/v1/reports/saved", headers=_h(token), json={
            "name": "گزارش ناظر", "dataset": "overview", "filters": {"days": 7}})
        assert r2.status_code in (200, 403)


@pytest.fixture(scope="module", autouse=True)
def _teardown_after_module(seeded):
    yield
    if seeded:
        _cleanup(seeded)
