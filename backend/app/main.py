# -*- coding: utf-8 -*-
"""نقطه ورود FastAPI — ارائه API و سرویس‌دهی رابط کاربری (build فرانت‌اند)."""
import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import Base, engine
from app.modules.identity.router import router as identity_router
from app.modules.organization.router import router as org_router
from app.modules.lookups.router import router as lookups_router
from app.modules.forms.router import router as forms_router
from app.modules.processes.router import router as processes_router
from app.modules.engine.router import router as engine_router
from app.modules.tasks.router import router as tasks_router
from app.modules.audit.router import router as audit_router
from app.modules.attachments.router import router as attachments_router
from app.modules.notifications.router import router as notifications_router
from app.modules.decisions.router import router as decisions_router
from app.modules.calendars.router import router as calendars_router
from app.modules.conditions.router import router as conditions_router
from app.modules.events.router import router as events_router
from app.modules.external.router import router as external_router
from app.modules.external.admin import router as integration_admin_router

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """قالب خطای یکسان + شناسه پیگیری."""
    import uuid
    detail = exc.detail
    if isinstance(detail, dict):
        body = {"error": detail, "trace_id": uuid.uuid4().hex[:12]}
    else:
        body = {"error": {"message": str(detail)}, "trace_id": uuid.uuid4().hex[:12]}
    return JSONResponse(status_code=exc.status_code, content=body)


# ---------- API v1 ----------
api = settings.API_V1_PREFIX
app.include_router(identity_router, prefix=api, tags=["identity"])
app.include_router(org_router, prefix=api, tags=["organization"])
app.include_router(lookups_router, prefix=api, tags=["lookups"])
app.include_router(forms_router, prefix=api, tags=["forms"])
app.include_router(processes_router, prefix=api, tags=["processes"])
app.include_router(engine_router, prefix=api, tags=["engine"])
app.include_router(tasks_router, prefix=api, tags=["tasks"])
app.include_router(audit_router, prefix=api, tags=["audit"])
app.include_router(attachments_router, prefix=api, tags=["attachments"])
app.include_router(notifications_router, prefix=api, tags=["notifications"])
app.include_router(decisions_router, prefix=api, tags=["decisions"])
app.include_router(calendars_router, prefix=api, tags=["calendars"])
app.include_router(conditions_router, prefix=api, tags=["conditions"])
app.include_router(events_router, prefix=api, tags=["events"])
app.include_router(external_router, prefix=api, tags=["external-api"])
app.include_router(integration_admin_router, prefix=api, tags=["integrations"])


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.on_event("startup")
def startup():
    # برای توسعه اولیه جداول ساخته می‌شود؛ مهاجرت رسمی با Alembic انجام می‌شود (سند §۲۷).
    try:
        # ایمپورت همه مدل‌ها برای ثبت در متادیتا
        from app.modules.identity import models  # noqa
        from app.modules.organization import models  # noqa
        from app.modules.lookups import router as _lr  # noqa (شامل مدل‌های Lookup)
        from app.modules.forms import models  # noqa
        from app.modules.engine import models  # noqa
        from app.modules.decisions import models  # noqa
        from app.modules.calendars import models  # noqa
        from app.modules.audit import service  # noqa
        from app.modules.attachments import router as _ar  # noqa (مدل Attachment)
        from app.modules.notifications import service  # noqa
        from app.modules.events import listeners  # noqa (ثبت شنونده after_commit)
        from app.modules.external import models  # noqa (مدل‌های API بیرونی — فاز ۵)
        from app.modules.external import webhooks  # noqa (شنونده ارسال Webhook پس از commit)
        Base.metadata.create_all(bind=engine)
    except Exception as e:  # pragma: no cover
        print("startup create_all warning:", e)


@app.on_event("startup")
async def startup_events():
    """فاز ۳: گذرگاه رویداد زنده (SSE) + زمان‌بند پایدار."""
    import asyncio
    from app.modules.events.bus import bus
    bus.set_loop(asyncio.get_running_loop())
    await bus.start_redis_bridge()
    if (settings.SCHEDULER_MODE or "inprocess").lower() == "inprocess":
        from app.worker.scheduler import scheduler
        scheduler.start()
    elif (settings.SCHEDULER_MODE or "").lower() == "celery":
        print("scheduler mode = celery — زمان‌بندی توسط Worker پایدار انجام می‌شود")


# ---------- سرویس‌دهی رابط کاربری ----------
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", "dist")

if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
