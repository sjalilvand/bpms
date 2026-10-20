# -*- coding: utf-8 -*-
"""آزمون‌های بانک سازمانی (فاز ۸) — فیلدهای سازمانی، بانک فرم‌ها و فرایندها."""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

_h = lambda t: {"Authorization": f"Bearer {t}"}
RUN = str(int(time.time()))  # کلیدهای یکتا برای اجرای مکرر روی دیتابیس ماندگار


@pytest.fixture(scope="module")
def api():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(api):
    r = api.post("/api/v1/auth/login", json={"username": "admin", "password": "Bpms@1234"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.usefixtures("admin_token")
class TestOrgFields:
    def test_crud_lifecycle(self, api, admin_token):
        h = _h(admin_token)
        # ثبت
        r = api.post("/api/v1/library/fields", headers=h, json={
            "key": f"personnel_code_t_{RUN}", "label": "کد پرسنلی آزمون", "type": "text",
            "category": "پرسنلی", "config_json": {"required": True}})
        assert r.status_code == 200, r.text
        fid = r.json()["id"]
        # فهرست
        r = api.get("/api/v1/library/fields", headers=h)
        assert any(x["key"] == f"personnel_code_t_{RUN}" for x in r.json()["items"])
        # کلید تکراری ممنوع
        r = api.post("/api/v1/library/fields", headers=h, json={
            "key": f"personnel_code_t_{RUN}", "label": "دوباره", "type": "text"})
        assert r.status_code == 400
        # ویرایش
        r = api.put(f"/api/v1/library/fields/{fid}", headers=h, json={
            "key": f"personnel_code_t_{RUN}", "label": "کد پرسنلی اصلاح", "type": "text",
            "category": "پرسنلی", "config_json": {}})
        assert r.status_code == 200
        assert r.json()["label"] == "کد پرسنلی اصلاح"
        # حذف
        r = api.delete(f"/api/v1/library/fields/{fid}", headers=h)
        assert r.status_code == 200


class TestFormTemplates:
    def test_instantiate_creates_draft_form(self, api, admin_token):
        h = _h(admin_token)
        schema = {"title": "فرم آزمون بانک", "fields": [
            {"key": "sample_text", "type": "text", "label": "متن", "colSpan": 8}]}
        r = api.post("/api/v1/library/forms", headers=h, json={
            "key": f"tpl_test_form_{RUN}", "title": "الگوی آزمون", "schema_json": schema})
        assert r.status_code == 200, r.text
        tid = r.json()["id"]
        # ساخت فرم از الگو
        r = api.post(f"/api/v1/library/forms/{tid}/instantiate", headers=h, json={
            "key": f"from_bank_form_t_{RUN}", "title": "فرم ساخته‌شده از بانک"})
        assert r.status_code == 200, r.text
        out = r.json()
        # فرم ساخته‌شده پیش‌نویس با فیلدهای الگو باشد
        r = api.get(f"/api/v1/forms/{out['id']}", headers=h)
        assert r.status_code == 200
        latest = r.json()["latest_version"]
        assert latest["status"] == "draft"
        # جزئیات نسخه شامل schema الگو
        r = api.get(f"/api/v1/forms/versions/{out['version_id']}", headers=h)
        assert r.status_code == 200
        assert r.json()["schema_json"]["fields"][0]["key"] == "sample_text"


class TestProcessTemplates:
    def test_add_from_existing_and_instantiate(self, api, admin_token):
        h = _h(admin_token)
        # فرایند نمونه seed — افزودن به بانک
        r = api.get("/api/v1/processes", headers=h)
        procs = r.json()["items"]
        assert procs, "فرایند نمونه موجود نیست"
        pid = procs[0]["id"]
        r = api.post(f"/api/v1/library/processes/from-existing/{pid}", headers=h, json={
            "key": f"tpl_test_proc_{RUN}"})
        assert r.status_code == 200, r.text
        tid = r.json()["id"]
        assert r.json()["has_bindings"] in (True, False)
        # ساخت فرایند جدید از الگو
        r = api.post(f"/api/v1/library/processes/{tid}/instantiate", headers=h, json={
            "key": f"from_bank_proc_t_{RUN}", "title": "فرایند ساخته‌شده از بانک"})
        assert r.status_code == 200, r.text
        out = r.json()
        r = api.get(f"/api/v1/processes/{out['id']}", headers=h)
        assert r.json()["latest_version"]["status"] == "draft"
        # جزئیات نسخه شامل BPMN الگو
        r = api.get(f"/api/v1/processes/versions/{out['version_id']}", headers=h)
        assert r.status_code == 200
        assert "<bpmn:definitions" in r.json()["bpmn_xml"]
