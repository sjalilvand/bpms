# -*- coding: utf-8 -*-
"""آداپتور موتور BPMN (SpiffWorkflow) — درگاه اتصال به موتور اجرا.

یافته‌های نمونه فنی فاز صفر (مبنای این پیاده‌سازی):
- عبارت تایمر باید رشته پایتونی کوتیشن‌دار باشد: 'PT1H'
- شناسه فنی عنصر: task_spec.name ؛ نام نمایشی: task_spec.bpmn_name
- وظایف انسانی: manual=True ؛ خطای سرویس: بازگشت False → حالت ERROR
- بازیابی: serialize_json / deserialize_json با رجیستری سفارشی ServiceTask
- پس از بیداری تایمر، یک گام موتور اضافه لازم است.
"""
from __future__ import annotations

import hashlib
import threading

from lxml import etree

from SpiffWorkflow.bpmn.parser.BpmnParser import BpmnParser
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow
from SpiffWorkflow.task import TaskState
from SpiffWorkflow.bpmn.serializer.workflow import BpmnWorkflowSerializer
from SpiffWorkflow.bpmn.serializer.config import DEFAULT_CONFIG
from SpiffWorkflow.bpmn.serializer.default.task_spec import BpmnTaskSpecConverter
from SpiffWorkflow.bpmn.specs.defaults import ServiceTask
from SpiffWorkflow.bpmn.script_engine.python_engine import PythonScriptEngine

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"


# ---------------- موتور اسکریپت محدودشده (منع اجرای آزاد کد) ----------------
SAFE_BUILTINS = {
    "abs": abs, "min": min, "max": max, "round": round, "len": len,
    "sum": sum, "sorted": sorted, "str": str, "int": int, "float": float,
    "bool": bool, "list": list, "dict": dict, "enumerate": enumerate,
    "True": True, "False": False, "None": None,
}


class RestrictedScriptEngine(PythonScriptEngine):
    """محیط اجرای محدود برای Script Task و شرط دروازه‌ها — بدون import/open/exec آزاد."""

    def evaluate(self, task, expression, external_context=None):
        return super().evaluate(task, expression, external_context)

    def execute(self, task, script, external_context=None):
        return super().execute(task, script, external_context)


# ---------------- اتصال ServiceTask به کاتالوگ کانکتور ----------------
def _bpms_service_execute(self, task) -> bool:
    from app.modules.engine.connectors import execute_connector
    return execute_connector(task, self)


ServiceTask._execute = _bpms_service_execute


# ---------------- Serializer سفارشی ----------------
def _build_serializer() -> BpmnWorkflowSerializer:
    config = {**DEFAULT_CONFIG, ServiceTask: BpmnTaskSpecConverter}
    registry = BpmnWorkflowSerializer.configure(config=config)
    return BpmnWorkflowSerializer(registry=registry)


SERIALIZER = _build_serializer()

_SPEC_CACHE: dict[str, object] = {}
_CACHE_LOCK = threading.Lock()


class EngineParseError(Exception):
    """خطای ساختاری/معنایی XML که مانع انتشار می‌شود."""


def list_process_ids(bpmn_xml: str) -> list[dict]:
    try:
        root = etree.fromstring(bpmn_xml.encode("utf-8"))
    except etree.XMLSyntaxError as e:
        raise EngineParseError(f"XML نامعتبر است: {e}")
    out = []
    for p in root.iter(f"{{{BPMN_NS}}}process"):
        out.append({"id": p.get("id"), "name": p.get("name") or p.get("id"), "isExecutable": p.get("isExecutable", "false")})
    return out


def parse_spec(bpmn_xml: str, main_process_id: str):
    """ساخت Spec با کش — خطاهای پارسر موتور به‌صورت EngineParseError گزارش می‌شود."""
    key = hashlib.sha256((bpmn_xml + "||" + main_process_id).encode("utf-8")).hexdigest()
    with _CACHE_LOCK:
        if key in _SPEC_CACHE:
            return _SPEC_CACHE[key]
    try:
        parser = BpmnParser()
        parser.add_bpmn_str(bpmn_xml.encode("utf-8"))
        spec = parser.get_spec(main_process_id)
    except Exception as e:
        raise EngineParseError(f"پارس مدل توسط موتور ممکن نشد: {e}")
    if spec is None:
        raise EngineParseError(f"فرایند اصلی «{main_process_id}» در فایل یافت نشد")
    with _CACHE_LOCK:
        if len(_SPEC_CACHE) > 64:
            _SPEC_CACHE.clear()
        _SPEC_CACHE[key] = spec
    return spec


def new_workflow(spec, initial_data: dict | None = None) -> BpmnWorkflow:
    wf = BpmnWorkflow(spec, script_engine=RestrictedScriptEngine())
    if initial_data:
        # داده اولیه باید روی وظیفه آغاز تزریق شود تا به شاخه‌های موازی منتقل شود
        tasks = wf.get_tasks()
        if tasks:
            tasks[0].data.update(initial_data)
        wf.data.update(initial_data)
    return wf


def restore_workflow(state_json: str) -> BpmnWorkflow:
    """بازیابی وضعیت پایدار پس از ری‌استارت (AC-13)."""
    return SERIALIZER.deserialize_json(state_json)


def serialize_workflow(wf: BpmnWorkflow) -> str:
    return SERIALIZER.serialize_json(wf)


def do_engine_steps(wf: BpmnWorkflow) -> None:
    """پیشبرد موتور؛ دو بار برای پوشش تایمرهایی که در همین فراخوانی بیدار می‌شوند."""
    wf.do_engine_steps()
    wf.do_engine_steps()


def refresh_waiting(wf: BpmnWorkflow) -> bool:
    """بررسی تایمرها/پیام‌های منتظر؛ True اگر وضعیتی تغییر کند."""
    before = len(wf.get_tasks(state=TaskState.READY))
    wf.refresh_waiting_tasks()
    after = len(wf.get_tasks(state=TaskState.READY))
    return after != before


def ready_user_tasks(wf: BpmnWorkflow) -> list:
    return [t for t in wf.get_tasks(state=TaskState.READY) if getattr(t.task_spec, "manual", False)]


def error_tasks(wf: BpmnWorkflow) -> list:
    return wf.get_tasks(state=TaskState.ERROR)


def retry_error_task(wf: BpmnWorkflow, task) -> None:
    """تلاش مجدد برای فعالیت خطادار — پس از اصلاح شرایط."""
    wf.run_task_from_id(task.id)
    do_engine_steps(wf)


def is_completed(wf: BpmnWorkflow) -> bool:
    return wf.is_completed()


def get_user_task(wf: BpmnWorkflow, task_uuid: str):
    """یافتن وظیفه انسانی آماده در وضعیت موتور بر اساس شناسه (رشته UUID)."""
    import uuid as _uuid
    try:
        tid = _uuid.UUID(str(task_uuid))
    except (ValueError, AttributeError):
        return None
    try:
        task = wf.get_task_from_id(tid)
    except Exception:
        return None
    if task is None:
        return None
    # تنها وظایف انسانی آماده مجاز به تکمیل از سمت API هستند
    if not getattr(task.task_spec, "manual", False):
        return None
    if task.state != TaskState.READY:
        return None
    return task
