# -*- coding: utf-8 -*-
"""فاز ۶ — API گزارش‌ساز و KPI.

- شاخص‌های کلی، گلوگاه‌ها، بار کاری و حجم روزانه با فیلتر بازه/فرایند/وضعیت
- گزارش‌های ذخیره‌شده (ذخیره پیکربندی و اجرای دوباره)
- فاز ۷ — خروجی Excel و PDF از همه مجموعه‌داده‌ها یا گزارش ذخیره‌شده
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_perm
from app.modules.identity.models import User
from app.modules.audit.service import log_action
from app.modules.reports import exporting, service
from app.modules.reports.models import SavedReport

router = APIRouter()

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class SavedReportIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str = ""
    dataset: str = Field(pattern="^(overview|bottlenecks|workload|volume)$")
    filters: dict = Field(default_factory=dict)


def _saved_out(r: SavedReport) -> dict:
    return {
        "id": r.id, "name": r.name, "description": r.description,
        "dataset": r.dataset, "filters": r.definition,
        "created_by_id": r.created_by_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


# ---------- KPI ها ----------

@router.get("/reports/kpi/overview")
def kpi_overview(days: int = 30, date_from: str = "", date_to: str = "",
                 definition_id: int = 0, status: str = "",
                 db: Session = Depends(get_db),
                 user: User = Depends(require_perm("report.view"))):
    try:
        return service.kpi_overview(
            db, days=days, date_from=date_from or None, date_to=date_to or None,
            definition_id=definition_id or None, status=status or None)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/reports/kpi/bottlenecks")
def kpi_bottlenecks(days: int = 30, date_from: str = "", date_to: str = "",
                    definition_id: int = 0,
                    db: Session = Depends(get_db),
                    user: User = Depends(require_perm("report.view"))):
    try:
        return {"items": service.kpi_bottlenecks(
            db, days=days, date_from=date_from or None, date_to=date_to or None,
            definition_id=definition_id or None)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/reports/kpi/workload")
def kpi_workload(days: int = 30, date_from: str = "", date_to: str = "",
                 definition_id: int = 0,
                 db: Session = Depends(get_db),
                 user: User = Depends(require_perm("report.view"))):
    try:
        return {"items": service.kpi_workload(
            db, days=days, date_from=date_from or None, date_to=date_to or None,
            definition_id=definition_id or None)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/reports/kpi/volume")
def kpi_volume(days: int = 30, date_from: str = "", date_to: str = "",
               definition_id: int = 0,
               db: Session = Depends(get_db),
               user: User = Depends(require_perm("report.view"))):
    try:
        return {"items": service.kpi_volume(
            db, days=days, date_from=date_from or None, date_to=date_to or None,
            definition_id=definition_id or None)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/reports/options")
def report_options(db: Session = Depends(get_db),
                   user: User = Depends(require_perm("report.view"))):
    """فهرست فرایندها برای فیلتر گزارش."""
    return {"processes": service.process_options(db)}


# ---------- گزارش‌های ذخیره‌شده ----------

@router.get("/reports/saved")
def list_saved(db: Session = Depends(get_db),
               user: User = Depends(require_perm("report.view"))):
    rows = db.scalars(select(SavedReport).order_by(SavedReport.id.desc())).all()
    return {"items": [_saved_out(r) for r in rows]}


@router.post("/reports/saved")
def create_saved(body: SavedReportIn, request: Request,
                 db: Session = Depends(get_db),
                 user: User = Depends(require_perm("report.manage"))):
    r = SavedReport(name=body.name.strip(), description=body.description,
                    dataset=body.dataset, definition=body.filters,
                    created_by_id=user.id)
    db.add(r)
    db.commit()
    log_action(db, user.id, "report.saved_created", "saved_report", r.id,
               {"name": r.name, "dataset": r.dataset}, request)
    db.commit()
    return _saved_out(r)


@router.delete("/reports/saved/{rid}")
def delete_saved(rid: int, request: Request,
                 db: Session = Depends(get_db),
                 user: User = Depends(require_perm("report.manage"))):
    r = db.get(SavedReport, rid)
    if not r:
        raise HTTPException(404, "گزارش ذخیره‌شده یافت نشد")
    if not user.is_superadmin and r.created_by_id not in (user.id, None):
        raise HTTPException(403, "فقط سازنده گزارش یا مدیر می‌تواند حذف کند")
    db.delete(r)
    db.commit()
    log_action(db, user.id, "report.saved_deleted", "saved_report", rid,
               {"name": r.name}, request)
    db.commit()
    return {"ok": True}


@router.get("/reports/saved/{rid}/run")
def run_saved(rid: int, db: Session = Depends(get_db),
              user: User = Depends(require_perm("report.view"))):
    r = db.get(SavedReport, rid)
    if not r:
        raise HTTPException(404, "گزارش ذخیره‌شده یافت نشد")
    try:
        data = service.run_saved(db, r.dataset, r.definition or {})
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"report": _saved_out(r), "data": data,
            "ran_at": datetime.now(timezone.utc).isoformat()}


# ---------- فاز ۷ — خروجی Excel / PDF ----------

def _export_filters(days: int = 30, date_from: str = "", date_to: str = "",
                    definition_id: int = 0, status: str = "") -> dict:
    return dict(days=days, date_from=date_from or None, date_to=date_to or None,
                definition_id=definition_id or None, status=status or None)


def _file_response(content: bytes, media_type: str, filename: str) -> Response:
    return Response(content, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Length": str(len(content)),
    })


def _export_name(fmt: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return f"bpms-report-{stamp}.{fmt}"


@router.get("/reports/export/excel")
def export_excel(days: int = 30, date_from: str = "", date_to: str = "",
                 definition_id: int = 0, status: str = "",
                 request: Request = None,
                 db: Session = Depends(get_db),
                 user: User = Depends(require_perm("report.view"))):
    """خروجی Excel — کتاب‌کار چندبرگی از همه مجموعه‌داده‌ها با فیلترهای فعلی."""
    try:
        data = exporting.collect_report(db, **_export_filters(days, date_from, date_to, definition_id, status))
        content = exporting.excel_bytes(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    log_action(db, user.id, "report.exported", "report", None,
               {"format": "excel", "days": days, "definition_id": definition_id}, request)
    db.commit()
    return _file_response(content, _XLSX_MIME, _export_name("xlsx"))


@router.get("/reports/export/pdf")
def export_pdf(days: int = 30, date_from: str = "", date_to: str = "",
               definition_id: int = 0, status: str = "",
               request: Request = None,
               db: Session = Depends(get_db),
               user: User = Depends(require_perm("report.view"))):
    """خروجی PDF فارسی (RTL) — سند کامل شاخص‌ها با فیلترهای فعلی."""
    try:
        data = exporting.collect_report(db, **_export_filters(days, date_from, date_to, definition_id, status))
        content = exporting.pdf_bytes(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    log_action(db, user.id, "report.exported", "report", None,
               {"format": "pdf", "days": days, "definition_id": definition_id}, request)
    db.commit()
    return _file_response(content, "application/pdf", _export_name("pdf"))


@router.get("/reports/saved/{rid}/export")
def export_saved(rid: int, format: str = Query(pattern="^(excel|pdf)$"),
                 request: Request = None,
                 db: Session = Depends(get_db),
                 user: User = Depends(require_perm("report.view"))):
    """خروجی Excel/PDF یک گزارش ذخیره‌شده (فقط مجموعه‌داده همان گزارش)."""
    r = db.get(SavedReport, rid)
    if not r:
        raise HTTPException(404, "گزارش ذخیره‌شده یافت نشد")
    f = r.definition or {}
    try:
        data = exporting.collect_report(
            db, days=int(f.get("days") or 30), date_from=f.get("date_from"),
            date_to=f.get("date_to"), definition_id=f.get("definition_id"),
            status=f.get("status"), dataset=r.dataset)
        if format == "excel":
            content = exporting.excel_bytes(data, report_name=f"گزارش ذخیره‌شده: {r.name}")
            return _file_response(content, _XLSX_MIME, f"bpms-saved-{rid}.xlsx")
        content = exporting.pdf_bytes(data, report_name=f"گزارش ذخیره‌شده: {r.name}")
        return _file_response(content, "application/pdf", f"bpms-saved-{rid}.pdf")
    except ValueError as e:
        raise HTTPException(400, str(e))
