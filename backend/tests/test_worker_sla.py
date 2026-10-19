# -*- coding: utf-8 -*-
"""تست پایش SLA و Worker پایدار (فاز ۳) — هشدار پیش از مهلت، فرازدگی، idempotency."""
from datetime import timedelta

from sqlalchemy import select

from app.core.database import SessionLocal
from app.modules.engine.models import EngineTask, ProcessInstance, ProcessDefinition, ProcessVersion
from app.modules.identity.models import User
from app.worker.sla import sla_check


def _make_task(db, *, due_offset_minutes: int | None, status="ready",
               claimed_by=None, assignee=None, candidate_role=None, spec="Task_ManagerApprove"):
    user = db.scalars(select(User).limit(1)).first()
    p = db.scalars(select(ProcessDefinition).limit(1)).first()
    v = db.scalars(select(ProcessVersion).where(ProcessVersion.definition_id == p.id).limit(1)).first()
    inst = ProcessInstance(definition_id=p.id, version_id=v.id, title="نمونه SLA",
                           started_by_id=user.id, engine_state="{}")
    db.add(inst)
    db.flush()
    from app.modules.engine.service import now
    due = (now() + timedelta(minutes=due_offset_minutes)) if due_offset_minutes is not None else None
    t = EngineTask(instance_id=inst.id, task_uuid="sla-test-uuid-1", spec_id=spec, name="تأیید مدیر",
                   status=status, assignee_id=assignee, candidate_role=candidate_role,
                   claimed_by_id=claimed_by, due_at=due, created_at=now() - timedelta(hours=8))
    db.add(t)
    db.commit()
    return t


class TestSlaCheck:
    def test_overdue_task_escalates_once(self):
        db = SessionLocal()
        try:
            t = _make_task(db, due_offset_minutes=-30, candidate_role="manager")
            res = sla_check(db)
            assert res["escalated"] >= 1
            db.refresh(t)
            assert t.sla_escalated_at is not None
            # فراخوانی مجدد — نباید دوباره اعلام شود (idempotent)
            res2 = sla_check(db)
            assert res2["escalated"] == 0
            # اعلان ثبت شده است
            assert db.scalars(select(EngineTask).where(EngineTask.id == t.id)).first() is not None
        finally:
            db.close()

    def test_warning_before_due(self):
        db = SessionLocal()
        try:
            # وظیفه ۸ ساعت پیش ایجاد شده، ۴ ساعت مانده → کل ۱۲ ساعت، ۶۶٪ گذشته → آستانه ۸۰٪ رد نشده
            # با آستانه ۵۰٪ باید هشدار بدهد
            t = _make_task(db, due_offset_minutes=240, candidate_role="manager")
            res = sla_check(db, warn_pct=50)
            assert res["warned"] >= 1
            db.refresh(t)
            assert t.sla_warned_at is not None
            res2 = sla_check(db, warn_pct=50)
            assert res2["warned"] == 0
        finally:
            db.close()

    def test_no_due_date_is_skipped(self):
        db = SessionLocal()
        try:
            t = _make_task(db, due_offset_minutes=None, candidate_role="manager")
            base_escalated = sla_check(db)
            db.refresh(t)
            assert t.sla_escalated_at is None
            assert t.sla_warned_at is None
        finally:
            db.close()

    def test_completed_task_not_checked(self):
        db = SessionLocal()
        try:
            t = _make_task(db, due_offset_minutes=-60, status="completed", candidate_role="manager")
            res = sla_check(db)
            db.refresh(t)
            assert t.sla_escalated_at is None
        finally:
            db.close()


class TestWorkerImpl:
    def test_tick_impl_runs(self):
        from app.worker.celery_app import _tick_impl, _sla_check_impl
        assert isinstance(_tick_impl(), int)
        res = _sla_check_impl()
        assert {"warned", "escalated", "checked"} <= set(res.keys())

    def test_beat_schedule_registered(self):
        try:
            from app.worker.celery_app import celery_app
        except ImportError:
            pytest.skip("Celery نصب نیست")
        schedule = celery_app.conf.beat_schedule
        assert "engine-tick-every-30s" in schedule
        assert "sla-check-every-5m" in schedule
        assert schedule["engine-tick-every-30s"]["task"] == "bpms.engine.tick"
        assert schedule["sla-check-every-5m"]["task"] == "bpms.tasks.sla_check"

    def test_task_functions_registered(self):
        try:
            from app.worker.celery_app import celery_app
        except ImportError:
            pytest.skip("Celery نصب نیست")
        assert "bpms.engine.tick" in celery_app.tasks
        assert "bpms.tasks.sla_check" in celery_app.tasks
