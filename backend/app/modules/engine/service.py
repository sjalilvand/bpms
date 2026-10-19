# -*- coding: utf-8 -*-
"""سرویس اجرای فرایند — هماهنگی موتور، وظایف، تاریخچه، اعلان و خطاها.

نکات طراحی طبق سند:
- هر نمونه به نسخه ثابت فرایند متصل می‌ماند؛ انتشار نسخه جدید نمونه‌های جاری را تغییر نمی‌دهد.
- وضعیت اجرا به‌صورت پایدار در engine_state ذخیره و پس از هر تغییر بازنویسی می‌شود.
- یک وظیفه هرگز دوبار تکمیل نمی‌شود (کنترل وضعیت + تراکنش).
- با موتور مستقل فرض تراکنش واحد نداریم؛ ذخیره وضعیت idempotent است.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.modules.engine import adapter
from app.modules.engine.models import (
    ProcessDefinition, ProcessVersion, ProcessInstance, EngineTask, InstanceEvent, Incident,
)
from app.modules.identity.models import User, utcnow
from app.modules.forms.models import FormVersion, FormSubmission
from app.modules.forms.validator import validate_form_data
from app.modules.notifications.service import notify_user, notify_role
from app.modules.audit.service import log_action


# ---------------- ابزارهای پایه ----------------
def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def add_event(db, instance_id, event_type, *, task_id=None, spec_id=None, task_name=None,
              actor_id=None, comment=None, detail=None):
    db.add(InstanceEvent(instance_id=instance_id, event_type=event_type, task_id=task_id,
                         spec_id=spec_id, task_name=task_name, actor_id=actor_id,
                         comment=comment, detail_json=detail or {}))


def _binding(version: ProcessVersion, spec_id: str) -> dict:
    return (version.config_json or {}).get("bindings", {}).get(spec_id, {}) or {}


def _resolve_form_version(db: Session, binding: dict) -> FormVersion | None:
    fid = binding.get("formDefinitionId")
    if not fid:
        return None
    return db.scalar(select(FormVersion).where(
        FormVersion.form_id == fid, FormVersion.status == "published").order_by(FormVersion.version.desc()))


def _resolve_assignee(db: Session, binding: dict, wf_data: dict, instance: ProcessInstance):
    """تخصیص بر اساس تنظیمات یا داده درخواست (قاعده سند §۵.۲)."""
    btype = binding.get("assigneeType", "role")
    value = binding.get("assigneeValue")
    if btype == "user":
        uid = int(value) if value else None
        return uid, None
    if btype == "role":
        return None, value
    if btype == "field":
        v = wf_data.get(value) if value else None
        if v is None:
            return None, None
        if isinstance(v, dict) and "id" in v:
            v = v["id"]
        try:
            return int(v), None
        except (TypeError, ValueError):
            return None, None
    if btype == "self":
        return instance.started_by_id, None
    return None, None


# ---------------- شروع نمونه ----------------
def start_instance(db: Session, version: ProcessVersion, user: User, *,
                   data: dict, business_key: str | None = None, title: str | None = None) -> ProcessInstance:
    spec = adapter.parse_spec(version.bpmn_xml, version.main_process_id)
    # فرم شروع: اعتبارسنجی نهایی در سرور
    start_binding = _binding(version, "start") or {}
    cleaned = data or {}
    if start_binding.get("formDefinitionId"):
        fv = _resolve_form_version(db, start_binding)
        if fv is None:
            raise ValueError("فرم شروع نسخه منتشرشده ندارد")
        r = validate_form_data(db, fv.schema_json, data or {})
        if not r.ok:
            raise ValueError({"message": "داده فرم شروع نامعتبر است", "errors": r.errors})
        cleaned = r.cleaned
    # داده اولیه باید روی وظیفه آغاز تزریق شود تا به شاخه‌های موازی منتقل شود
    initial = dict(cleaned)
    initial["_initiator_id"] = user.id
    initial["business_key"] = business_key
    connectors_map = {spec_id: b["connector"] for spec_id, b in
                      (version.config_json or {}).get("bindings", {}).items() if b.get("connector")}
    if connectors_map:
        initial["_connectors"] = connectors_map
    wf = adapter.new_workflow(spec, initial)
    adapter.do_engine_steps(wf)

    definition = db.get(ProcessDefinition, version.definition_id)
    inst = ProcessInstance(
        definition_id=version.definition_id, version_id=version.id,
        title=title or definition.title, business_key=business_key,
        started_by_id=user.id, engine_state=adapter.serialize_workflow(wf),
    )
    db.add(inst)
    db.flush()
    add_event(db, inst.id, "instance_started", actor_id=user.id,
              detail={"version": version.version, "process": definition.key})
    _sync_tasks(db, inst, wf)
    db.commit()
    log_action(db, user.id, "instance.started", "instance", inst.id, {"process": definition.key})
    return inst


# ---------------- همگام‌سازی وظایف ----------------
def _sync_tasks(db: Session, instance: ProcessInstance, wf) -> None:
    """تطبیق صف کارتابل با وضعیت موتور + اعلان و تاریخچه."""
    version = instance.version
    active = adapter.ready_user_tasks(wf)
    active_uuids = {str(t.id) for t in active}

    open_rows = db.scalars(select(EngineTask).where(
        EngineTask.instance_id == instance.id,
        EngineTask.status.in_(["ready", "claimed"]))).all()
    open_uuids = {r.task_uuid for r in open_rows}

    for t in active:
        uid = str(t.id)
        if uid in open_uuids:
            continue
        spec = t.task_spec
        binding = _binding(version, spec.name)
        fv = _resolve_form_version(db, binding)
        assignee_id, candidate_role = _resolve_assignee(db, binding, t.data or {}, instance)
        due_hours = binding.get("dueHours")
        row = EngineTask(
            instance_id=instance.id, task_uuid=uid, spec_id=spec.name,
            name=getattr(spec, "bpmn_name", None) or spec.name, task_type="user",
            status="ready", assignee_id=assignee_id, candidate_role=candidate_role,
            form_version_id=fv.id if fv else None,
            due_at=(now() + timedelta(hours=float(due_hours))) if due_hours else None,
        )
        db.add(row)
        db.flush()
        add_event(db, instance.id, "task_created", task_id=row.id, spec_id=spec.name, task_name=row.name)
        if assignee_id:
            notify_user(db, assignee_id, "وظیفه جدید", f"«{row.name}» در فرایند «{instance.title}» به شما تخصیص یافت",
                        link=f"/inbox?task={row.id}")
        elif candidate_role:
            notify_role(db, candidate_role, "وظیفه گروهی جدید", f"«{row.name}» در فرایند «{instance.title}» به صف گروهی افزوده شد",
                        link=f"/inbox?task={row.id}")

    # وظایفی که در موتور دیگر فعال نیستند → لغو (مثلاً پس از ادغام موازی)
    for row in open_rows:
        if row.task_uuid not in active_uuids:
            row.status = "cancelled"
            add_event(db, instance.id, "task_cancelled", task_id=row.id, spec_id=row.spec_id, task_name=row.name)


# ---------------- دریافت وضعیت موتور ----------------
def load_workflow(instance: ProcessInstance):
    """بازیابی وضعیت از engine_state + بررسی تایمرها."""
    wf = adapter.restore_workflow(instance.engine_state)
    changed = adapter.refresh_waiting(wf)
    if changed:
        adapter.do_engine_steps(wf)
    return wf


def save_workflow(db: Session, instance: ProcessInstance, wf) -> None:
    instance.engine_state = adapter.serialize_workflow(wf)


def _check_completed(db: Session, instance: ProcessInstance, wf, actor_id=None):
    if adapter.is_completed(wf) and instance.status == "running":
        instance.status = "completed"
        instance.finished_at = now()
        add_event(db, instance.id, "instance_completed", actor_id=actor_id)


def _check_incidents(db: Session, instance: ProcessInstance, wf) -> None:
    for t in adapter.error_tasks(wf):
        msg = (t.data or {}).get("_last_connector_error") or (t.data or {}).get("_last_error") or "خطای اجرای فعالیت سیستمی"
        existing = db.scalar(select(Incident).where(
            Incident.instance_id == instance.id, Incident.task_uuid == str(t.id), Incident.resolved_at.is_(None)))
        if not existing:
            db.add(Incident(instance_id=instance.id, task_uuid=str(t.id), spec_id=t.task_spec.name,
                            message=str(msg)[:1000], detail_json={"name": getattr(t.task_spec, "bpmn_name", "")}))
            add_event(db, instance.id, "incident_created", spec_id=t.task_spec.name,
                      task_name=getattr(t.task_spec, "bpmn_name", None), detail={"message": str(msg)[:500]})


# ---------------- تکمیل وظیفه ----------------
def complete_task(db: Session, task: EngineTask, user: User, *, data: dict | None,
                  result: str | None, comment: str | None, partial: bool = False) -> EngineTask:
    if task.status not in ("ready", "claimed"):
        raise ValueError("این وظیفه قابل تکمیل نیست")
    if task.status == "claimed" and task.claimed_by_id != user.id and not user.is_superadmin:
        raise ValueError("این وظیفه توسط کاربر دیگری دریافت شده است")
    if task.status == "ready" and task.assignee_id and task.assignee_id != user.id and not user.is_superadmin:
        raise ValueError("این وظیفه به شما تخصیص نیافته است")
    if task.status == "ready" and task.candidate_role and not user.is_superadmin:
        raise ValueError("برای تکمیل وظیفه گروهی، ابتدا آن را دریافت کنید")

    instance = db.get(ProcessInstance, task.instance_id)
    if instance.status != "running":
        raise ValueError("نمونه اجرایی در وضعیت جاری نیست")
    wf = load_workflow(instance)
    engine_task = adapter.get_user_task(wf, task.task_uuid)
    if engine_task is None:
        raise ValueError("وظیفه در وضعیت موتور یافت نشد؛ صفحه را بازآوری کنید")

    # اعتبارسنجی فرم در سرور (مرجع نهایی) — روی ادغام داده موجود و داده جدید
    cleaned = data or {}
    if task.form_version_id:
        fv = db.get(FormVersion, task.form_version_id)
        if fv:
            merged = {**(engine_task.data or {}), **(data or {})}
            r = validate_form_data(db, fv.schema_json, merged, partial=partial)
            if not r.ok and not partial:
                raise ValueError({"message": "داده فرم نامعتبر است", "errors": r.errors})
            cleaned = r.cleaned
    engine_task.data.update(cleaned)
    if result:
        engine_task.data["action"] = result
    if comment:
        engine_task.data["_comment"] = comment

    engine_task.complete()
    adapter.do_engine_steps(wf)

    task.status = "completed"
    task.completed_at = now()
    task.completed_by_id = user.id
    task.data_json = cleaned
    task.result = result
    task.comment = comment
    db.flush()
    add_event(db, instance.id, "task_completed", task_id=task.id, spec_id=task.spec_id, task_name=task.name,
              actor_id=user.id, comment=comment, detail={"result": result})

    _sync_tasks(db, instance, wf)
    _check_incidents(db, instance, wf)
    _check_completed(db, instance, wf, actor_id=user.id)
    save_workflow(db, instance, wf)

    db.add(FormSubmission(form_version_id=task.form_version_id, instance_id=instance.id, task_id=task.id,
                          data_json=cleaned, submitted_by_id=user.id, status="draft" if partial else "final"))
    db.commit()
    log_action(db, user.id, "task.completed", "task", task.id, {"instance": instance.id, "result": result})
    return task


def claim_task(db: Session, task: EngineTask, user: User) -> EngineTask:
    """دریافت وظیفه از صف گروهی با کنترل رقابت (AC-12)."""
    if task.status != "ready":
        raise ValueError("وظیفه در وضعیت قابل دریافت نیست")
    if task.assignee_id and task.assignee_id != user.id:
        raise ValueError("وظیفه به کاربر دیگری تخصیص یافته است")
    if task.candidate_role and not user.is_superadmin:
        user_roles = [r.code for r in user.roles]
        if task.candidate_role not in user_roles:
            raise ValueError("عضو گروه نامزد این وظیفه نیستید")
    task.status = "claimed"
    task.claimed_by_id = user.id
    task.claimed_at = now()
    db.flush()
    add_event(db, task.instance_id, "task_claimed", task_id=task.id, spec_id=task.spec_id,
              task_name=task.name, actor_id=user.id)
    db.commit()
    return task


def release_task(db: Session, task: EngineTask, user: User) -> EngineTask:
    if task.status != "claimed" or task.claimed_by_id != user.id:
        raise ValueError("فقط دریافت‌کننده وظیفه می‌تواند آن را آزاد کند")
    task.status = "ready"
    task.claimed_by_id = None
    task.claimed_at = None
    db.flush()
    add_event(db, task.instance_id, "task_released", task_id=task.id, spec_id=task.spec_id, task_name=task.name, actor_id=user.id)
    db.commit()
    return task


# ---------------- لغو و مداخله مدیر ----------------
def cancel_instance(db: Session, instance: ProcessInstance, user: User, reason: str = ""):
    if instance.status != "running":
        raise ValueError("نمونه در وضعیت جاری نیست")
    wf = adapter.restore_workflow(instance.engine_state)
    try:
        wf.cancel()
    except Exception:
        pass
    for row in db.scalars(select(EngineTask).where(
            EngineTask.instance_id == instance.id, EngineTask.status.in_(["ready", "claimed"]))).all():
        row.status = "cancelled"
    instance.status = "cancelled"
    instance.finished_at = now()
    instance.engine_state = adapter.serialize_workflow(wf)
    add_event(db, instance.id, "instance_cancelled", actor_id=user.id, comment=reason)
    db.commit()
    log_action(db, user.id, "instance.cancelled", "instance", instance.id, {"reason": reason})


def retry_incident(db: Session, incident: Incident, user: User):
    """رسیدگی کنترل‌شده به خطا: تلاش مجدد فعالیت خطادار."""
    if incident.resolved_at:
        raise ValueError("این مورد قبلاً رسیدگی شده است")
    instance = db.get(ProcessInstance, incident.instance_id)
    wf = adapter.restore_workflow(instance.engine_state)
    err = [t for t in adapter.error_tasks(wf) if str(t.id) == incident.task_uuid]
    if not err:
        raise ValueError("فعالیت خطادار متناظر یافت نشد")
    t = err[0]
    t.data.pop("_last_connector_error", None)
    t.data.pop("_last_connector_result", None)
    t.data["_last_error"] = None
    adapter.retry_error_task(wf, t)
    _sync_tasks(db, instance, wf)
    _check_incidents(db, instance, wf)
    _check_completed(db, instance, wf, actor_id=user.id)
    save_workflow(db, instance, wf)
    incident.resolved_at = now()
    add_event(db, instance.id, "incident_resolved", spec_id=incident.spec_id, actor_id=user.id)
    db.commit()
    log_action(db, user.id, "incident.resolved", "incident", incident.id, {"instance": instance.id})


# ---------------- زمان‌بند سبک (تایمرها) ----------------
def tick(db: Session, limit: int = 100) -> int:
    """بررسی نمونه‌های در جریان برای بیدارشدن تایمرها — فراخوانی دوره‌ای یا پس از هر تعامل.

    در فاز عملیاتی این کار به Worker/صف پایدار منتقل می‌شود (سند §۲۱).
    """
    touched = 0
    rows = db.scalars(select(ProcessInstance).where(ProcessInstance.status == "running").limit(limit)).all()
    for instance in rows:
        try:
            wf = adapter.restore_workflow(instance.engine_state)
            changed = adapter.refresh_waiting(wf)
            if changed:
                adapter.do_engine_steps(wf)
                _sync_tasks(db, instance, wf)
                _check_incidents(db, instance, wf)
                _check_completed(db, instance, wf)
                save_workflow(db, instance, wf)
                touched += 1
        except Exception:
            continue
    db.commit()
    return touched
