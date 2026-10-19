# -*- coding: utf-8 -*-
"""Worker پایدار (Celery) — زمان‌بند تایمرها و پایش SLA (سند §۲۱ فاز ۳).

اجرا در عملیات:
    celery -A app.worker.celery_app worker --loglevel=info -Q bpms
    celery -A app.worker.celery_app beat   # یا worker -B برای نمونه‌های کوچک

زمان‌بندی beat:
- engine.tick        هر ۳۰ ثانیه  → بیدار کردن تایمرهای BPMN منتظر (Duration/Date)
- tasks.sla_check    هر ۵ دقیقه   → هشدار/فرازدگی مهلت وظایف

اگر Redis/Celery در دسترس نباشد، برنامه uvicorn با زمان‌بند درون‌فرایندی
(app.worker.scheduler) همان کارها را با فاصله سبک‌تر انجام می‌دهد.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("bpms.worker")


def _settings():
    from app.core.config import settings
    return settings


try:
    from celery import Celery
except ImportError:  # pragma: no cover — Celery اختیاری است
    Celery = None

_s = _settings()
BROKER_URL = _s.CELERY_BROKER_URL
RESULT_BACKEND = _s.CELERY_RESULT_BACKEND or BROKER_URL

if Celery is not None:
    celery_app = Celery(
        "bpms",
        broker=BROKER_URL,
        backend=RESULT_BACKEND,
        include=["app.worker.celery_app"],
    )
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_default_queue="bpms",
        beat_schedule={
            "engine-tick-every-30s": {
                "task": "bpms.engine.tick",
                "schedule": 30.0,
            },
            "sla-check-every-5m": {
                "task": "bpms.tasks.sla_check",
                "schedule": 300.0,
            },
        },
        task_time_limit=120,
        task_soft_time_limit=100,
        worker_prefetch_multiplier=1,
    )
else:  # pragma: no cover
    celery_app = None


def _session():
    from app.core.database import SessionLocal
    return SessionLocal()


def _tick_impl() -> int:
    """یک گام تیک موتور — بررسی تایمرهای نمونه‌های در جریان."""
    from app.modules.engine import service as svc
    db = _session()
    try:
        return svc.tick(db)
    except Exception as e:
        logger.warning("engine tick failed: %s", e)
        return 0
    finally:
        db.close()


def _sla_check_impl() -> dict:
    from app.worker.sla import sla_check
    db = _session()
    try:
        return sla_check(db)
    except Exception as e:
        logger.warning("sla check failed: %s", e)
        return {"warned": 0, "escalated": 0, "checked": 0, "error": str(e)[:200]}
    finally:
        db.close()


if Celery is not None:
    @celery_app.task(name="bpms.engine.tick", ignore_result=True)
    def engine_tick_task():
        return _tick_impl()

    @celery_app.task(name="bpms.tasks.sla_check", ignore_result=True)
    def sla_check_task():
        return _sla_check_impl()
