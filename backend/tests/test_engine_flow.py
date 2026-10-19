# -*- coding: utf-8 -*-
"""تست انطباق موتور اجرا — نمونه فنی فاز صفر (سند §۸.۳) و AC-10/11/12/13/14.

سناریو: شروع → وظیفه انسانی → شرط → موازی → سرویس → پایان
همچنین: حلقه اصلاح، رد، خطای سرویس + Incident + retry، بازیابی وضعیت.
"""
import json

import pytest

from app.core.database import SessionLocal
from app.modules.engine import adapter
from app.modules.engine.models import ProcessVersion
from SpiffWorkflow.task import TaskState


BPMN = open("data/bpmn/purchase_request.bpmn", encoding="utf-8").read()


@pytest.fixture()
def spec():
    return adapter.parse_spec(BPMN, "Process_PurchaseRequest")


CONNECTORS = {"Task_RegisterOrder": "mock:register_order"}


def _ready(wf):
    return adapter.ready_user_tasks(wf)


def _by_name(wf, name):
    ts = [t for t in _ready(wf) if t.task_spec.bpmn_name == name]
    assert ts, f"وظیفه «{name}» یافت نشد؛ فعال‌ها: {[t.task_spec.bpmn_name for t in _ready(wf)]}"
    return ts[0]


class TestEngineFlow:
    def test_start_reaches_submit_task(self, spec):
        wf = adapter.new_workflow(spec, {"_initiator_id": 8, "total_amount": 100, "_connectors": CONNECTORS})
        adapter.do_engine_steps(wf)
        names = [t.task_spec.bpmn_name for t in _ready(wf)]
        assert names == ["ثبت درخواست خرید"]

    def test_full_approve_flow_with_parallel(self, spec):
        wf = adapter.new_workflow(spec, {"_initiator_id": 8, "_connectors": CONNECTORS})
        adapter.do_engine_steps(wf)
        t = _by_name(wf, "ثبت درخواست خرید")
        t.data["total_amount"] = 5_000_000
        t.complete(); adapter.do_engine_steps(wf)

        t2 = _by_name(wf, "تأیید مدیر")
        t2.data["action"] = "approve"
        t2.complete(); adapter.do_engine_steps(wf)

        # انشعاب موازی: اطلاع‌رسانی مالی فعال
        names = {t.task_spec.bpmn_name for t in _ready(wf)}
        assert "اطلاع‌رسانی مالی" in names
        # اطلاع‌رسانی مالی تکمیل → اتصال موازی → خروجی سرویس به متغیرهای ریشه ادغام می‌شود
        _by_name(wf, "اطلاع‌رسانی مالی").complete(); adapter.do_engine_steps(wf)
        assert adapter.is_completed(wf)
        assert wf.data.get("order_id"), "سرویس ثبت سفارش باید اجرا شده باشد"

    def test_reject_path(self, spec):
        wf = adapter.new_workflow(spec, {"_connectors": CONNECTORS})
        adapter.do_engine_steps(wf)
        _by_name(wf, "ثبت درخواست خرید").complete(); adapter.do_engine_steps(wf)
        t = _by_name(wf, "تأیید مدیر")
        t.data["action"] = "reject"
        t.complete(); adapter.do_engine_steps(wf)
        assert adapter.is_completed(wf)
        assert not wf.data.get("order_id")

    def test_revision_loop(self, spec):
        wf = adapter.new_workflow(spec, {"_connectors": CONNECTORS})
        adapter.do_engine_steps(wf)
        _by_name(wf, "ثبت درخواست خرید").complete(); adapter.do_engine_steps(wf)
        t = _by_name(wf, "تأیید مدیر")
        t.data["action"] = "revision"
        t.complete(); adapter.do_engine_steps(wf)
        # بازگشت به ثبت درخواست
        names = [t.task_spec.bpmn_name for t in _ready(wf)]
        assert "ثبت درخواست خرید" in names

    def test_serialize_restore_after_restart(self, spec):
        """AC-13: بازیابی وضعیت اجرا پس از راه‌اندازی مجدد."""
        wf = adapter.new_workflow(spec, {"_connectors": CONNECTORS})
        adapter.do_engine_steps(wf)
        _by_name(wf, "ثبت درخواست خرید").data["total_amount"] = 100
        _by_name(wf, "ثبت درخواست خرید").complete(); adapter.do_engine_steps(wf)
        state = adapter.serialize_workflow(wf)

        # «ری‌استارت»: ساخت workflow جدید از وضعیت ذخیره‌شده
        wf2 = adapter.restore_workflow(state)
        names = [t.task_spec.bpmn_name for t in _ready(wf2)]
        assert names == ["تأیید مدیر"]
        t = _by_name(wf2, "تأیید مدیر")
        assert t.data["total_amount"] == 100  # متغیرها حفظ شده‌اند
        t.data["action"] = "approve"
        t.complete(); adapter.do_engine_steps(wf2)
        names = {t.task_spec.bpmn_name for t in _ready(wf2)}
        assert "اطلاع‌رسانی مالی" in names
        _by_name(wf2, "اطلاع‌رسانی مالی").complete(); adapter.do_engine_steps(wf2)
        assert adapter.is_completed(wf2)
        assert wf2.data.get("order_id")

    def test_version_snapshot_independence(self, spec):
        """AC-14: درخواست‌های جاری به نسخه ثابت متصل می‌مانند (مدل سطح سرویس؛
        اینجا اطمینان از مستقل‌بودن state سریالایز از spec است)."""
        wf = adapter.new_workflow(spec, {"_connectors": CONNECTORS})
        adapter.do_engine_steps(wf)
        state = adapter.serialize_workflow(wf)
        # تغییر spec جدید (مثل انتشار نسخه ۲) نباید state قبلی را خراب کند
        adapter.parse_spec(BPMN, "Process_PurchaseRequest")  # از کش
        wf2 = adapter.restore_workflow(state)
        assert [t.task_spec.bpmn_name for t in _ready(wf2)] == ["ثبت درخواست خرید"]

    def test_unsupported_construct_rejected(self):
        """AC-02: مدل دارای عنصر پشتیبانی‌نشده نباید منتشر/اجرا شود."""
        bad = BPMN.replace('name="ثبت سفارش (سرویس)"', 'name="x"').replace(
            "<bpmn:serviceTask", "<bpmn:businessRuleTask", 1)
        with pytest.raises(adapter.EngineParseError):
            adapter.parse_spec(bad, "Process_PurchaseRequest")


class TestServiceFailure:
    def test_service_error_creates_error_task_then_retry(self, spec, monkeypatch):
        """AC-15: خطای سرویس → مورد قابل رسیدگی → تلاش مجدد کنترل‌شده."""
        from app.modules.engine import connectors

        failing = {"on": True}

        def fake_run(ref, data):
            if failing["on"]:
                raise RuntimeError("service unavailable")
            return {"order_id": "SO-OK"}

        monkeypatch.setattr(connectors, "_run", fake_run)
        wf = adapter.new_workflow(spec, {"_connectors": CONNECTORS})
        adapter.do_engine_steps(wf)
        _by_name(wf, "ثبت درخواست خرید").complete(); adapter.do_engine_steps(wf)
        t = _by_name(wf, "تأیید مدیر")
        t.data["action"] = "approve"
        t.complete(); adapter.do_engine_steps(wf)

        errs = adapter.error_tasks(wf)
        assert [t.task_spec.name for t in errs] == ["Task_RegisterOrder"]
        assert not adapter.is_completed(wf)

        # رفع خطا و تلاش مجدد
        failing["on"] = False
        adapter.retry_error_task(wf, errs[0])
        # شاخه موازی مالی همچنان باز است
        names = {t.task_spec.bpmn_name for t in _ready(wf)}
        assert "اطلاع‌رسانی مالی" in names
        _by_name(wf, "اطلاع‌رسانی مالی").complete(); adapter.do_engine_steps(wf)
        assert adapter.is_completed(wf)
        assert wf.data.get("order_id") == "SO-OK"

    def test_timer_duration_and_firing(self):
        bpmn_timer = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" id="D" targetNamespace="t">
<bpmn:process id="P" isExecutable="true">
<bpmn:startEvent id="S"><bpmn:outgoing>FA</bpmn:outgoing></bpmn:startEvent>
<bpmn:userTask id="TA" name="کار"><bpmn:incoming>FA</bpmn:incoming><bpmn:outgoing>FB</bpmn:outgoing></bpmn:userTask>
<bpmn:sequenceFlow id="FA" sourceRef="S" targetRef="TA"/>
<bpmn:sequenceFlow id="FB" sourceRef="TA" targetRef="TE"/>
<bpmn:intermediateCatchEvent id="TE" name="انتظار یک ثانیه"><bpmn:incoming>FB</bpmn:incoming><bpmn:outgoing>FC</bpmn:outgoing>
<bpmn:timerEventDefinition><bpmn:timeDuration xsi:type="bpmn:tFormalExpression">'PT1S'</bpmn:timeDuration></bpmn:timerEventDefinition>
</bpmn:intermediateCatchEvent>
<bpmn:sequenceFlow id="FC" sourceRef="TE" targetRef="E"/>
<bpmn:endEvent id="E"><bpmn:incoming>FC</bpmn:incoming></bpmn:endEvent>
</bpmn:process></bpmn:definitions>"""
        import time
        spec_t = adapter.parse_spec(bpmn_timer, "P")
        wf = adapter.new_workflow(spec_t)
        adapter.do_engine_steps(wf)
        _by_name(wf, "کار").complete(); adapter.do_engine_steps(wf)
        waiting = [t for t in wf.get_tasks() if t.state == TaskState.WAITING]
        assert waiting, "باید روی تایمر منتظر بماند"
        state = adapter.serialize_workflow(wf)
        time.sleep(1.2)
        wf2 = adapter.restore_workflow(state)
        adapter.do_engine_steps(wf2)
        assert adapter.is_completed(wf2), "پس از گذشت مهلت، تایمر باید بیدار شود"
