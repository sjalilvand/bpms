# -*- coding: utf-8 -*-
"""زمان‌بند درون‌فرایندی — جایگزین سبک Celery برای توسعه و پایلوت.

اگر BPMS_SCHEDULER_MODE=inprocess باشد (پیش‌فرض)، uvicorn در startup این
زمان‌بند را با نخ پس‌زمینه اجرا می‌کند:
- تیک موتور هر BPMS_TICK_SECONDS (پیش‌فرض ۳۰) ثانیه
- بررسی SLA هر BPMS_SLA_SECONDS (پیش‌فرض ۳۰۰) ثانیه

در عملیات با Celery: BPMS_SCHEDULER_MODE=celery تنظیم می‌شود تا از تکرار
جلوگیری شود (فقط worker Celery زمان‌بندی می‌کند).
"""
from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger("bpms.scheduler")

_started = threading.Event()


class InProcessScheduler:
    def __init__(self):
        try:
            from app.core.config import settings
            self.tick_seconds = float(settings.TICK_SECONDS or 30)
            self.sla_seconds = float(settings.SLA_SECONDS or 300)
        except Exception:
            self.tick_seconds = float(os.environ.get("BPMS_TICK_SECONDS", "30") or 30)
            self.sla_seconds = float(os.environ.get("BPMS_SLA_SECONDS", "300") or 300)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_sla = 0.0

    def start(self):
        if _started.is_set():
            return
        self._thread = threading.Thread(target=self._run, name="bpms-scheduler", daemon=True)
        self._thread.start()
        _started.set()
        logger.info("in-process scheduler started (tick=%ss, sla=%ss)", self.tick_seconds, self.sla_seconds)

    def stop(self):
        self._stop.set()
        _started.clear()

    def _run(self):
        # کمی صبر اولیه تا برنامه بالا بیاید
        self._stop.wait(5)
        while not self._stop.is_set():
            try:
                from app.worker.celery_app import _tick_impl, _sla_check_impl
                touched = _tick_impl()
                if touched:
                    logger.debug("tick touched %s instances", touched)
                if time.monotonic() - self._last_sla >= self.sla_seconds:
                    self._last_sla = time.monotonic()
                    _sla_check_impl()
            except Exception as e:  # pragma: no cover
                logger.warning("scheduler cycle failed: %s", e)
            self._stop.wait(self.tick_seconds)


scheduler = InProcessScheduler()
