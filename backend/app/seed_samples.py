# -*- coding: utf-8 -*-
"""نمونه‌پروژه‌های صفر تا صد (فاز ۸) — اجرا: python -m app.seed_samples

هر نمونه شامل: فرم‌های طراحی‌شده + مدل BPMN با DI + اتصال فرم/مسئول/نتیجه + انتشار نسخه.
نمونه‌ها:
  ۱) مرخصی کارکنان (حضور و غیاب)  ۲) اصلاح تردد (حضور و غیاب)
  ۳) مستندسازی اسناد سازمانی      ۴) ماموریت اداری
  ۵) تیکت پشتیبانی فناوری اطلاعات
همچنین: فیلدهای سازمانی + ثبت الگوها در بانک سازمانی.
همه گام‌ها idempotent هستند و با اجرای مجدد داده تکراری نمی‌سازند.
"""
import os
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import SessionLocal, Base, engine
from app.core.security import hash_password
from app.modules.identity.models import Role, User
from app.modules.organization.models import OrganizationUnit
from app.modules.lookups.router import LookupDefinition, LookupItem
from app.modules.forms.models import FormDefinition, FormVersion
from app.modules.engine.models import ProcessDefinition, ProcessVersion
from app.modules.library.models import OrgField, FormTemplate, ProcessTemplate
from app.seed_bpmn import Node, Flow, build_bpmn
from app.seed import DEFAULT_PASSWORD

BPMN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bpmn")


# ============================== BPMN مدل‌ها ==============================

def bpmn_leave_request() -> tuple[str, str]:
    """۱) مرخصی کارکنان — ثبت، تأیید سرپرست، ارجاع منابع انسانی برای بیش از ۳ روز."""
    nodes = [
        Node("Start_Leave", "startEvent", "ثبت درخواست مرخصی", 140, 252),
        Node("Task_SubmitLeave", "userTask", "ثبت درخواست مرخصی", 220, 230),
        Node("Task_SupervisorApprove", "userTask", "تأیید سرپرست", 390, 230),
        Node("GW_Supervisor", "exclusiveGateway", "تصمیم سرپرست", 560, 245, default_flow="Flow_Leave_Reject"),
        Node("End_Leave_Rejected", "endEvent", "رد شده", 566, 380),
        Node("GW_Days", "exclusiveGateway", "بررسی مدت مرخصی", 670, 245, default_flow="Flow_Days_Short"),
        Node("Task_HRApprove", "userTask", "تأیید منابع انسانی", 790, 230),
        Node("End_Leave_Approved", "endEvent", "تأیید نهایی", 970, 252),
    ]
    flows = [
        Flow("F_Start_Submit", "Start_Leave", "Task_SubmitLeave"),
        Flow("F_Submit_Sup", "Task_SubmitLeave", "Task_SupervisorApprove"),
        Flow("F_Sup_GW", "Task_SupervisorApprove", "GW_Supervisor"),
        Flow("Flow_Leave_Reject", "GW_Supervisor", "End_Leave_Rejected", name="رد"),
        Flow("Flow_Leave_Approve", "GW_Supervisor", "GW_Days", name="تأیید", cond="action == 'approve'"),
        Flow("Flow_Days_HR", "GW_Days", "Task_HRApprove", name="بیش از ۳ روز", cond="days_count > 3"),
        Flow("Flow_Days_Short", "GW_Days", "End_Leave_Approved", name="۳ روز یا کمتر"),
        Flow("F_HR_End", "Task_HRApprove", "End_Leave_Approved"),
    ]
    return build_bpmn("Definitions_Leave", "http://bpms.local/leave",
                      "Process_LeaveRequest", "مرخصی کارکنان", nodes, flows), "Process_LeaveRequest"


def bpmn_attendance_correction() -> tuple[str, str]:
    """۲) اصلاح تردد — ثبت مغایرت ورود/خروج و بررسی سرپرست."""
    nodes = [
        Node("Start_Corr", "startEvent", "ثبت درخواست اصلاح تردد", 140, 232),
        Node("Task_SubmitCorr", "userTask", "ثبت مغایرت تردد", 220, 210),
        Node("Task_SupervisorCheck", "userTask", "بررسی سرپرست", 390, 210),
        Node("GW_Corr", "exclusiveGateway", "تصمیم سرپرست", 560, 225, default_flow="Flow_Corr_Reject"),
        Node("End_CorrRejected", "endEvent", "رد شده", 566, 350),
        Node("End_CorrApproved", "endEvent", "اصلاح تأیید شد", 690, 232),
    ]
    flows = [
        Flow("F_Corr_Start", "Start_Corr", "Task_SubmitCorr"),
        Flow("F_Corr_Check", "Task_SubmitCorr", "Task_SupervisorCheck"),
        Flow("F_Corr_GW", "Task_SupervisorCheck", "GW_Corr"),
        Flow("Flow_Corr_Reject", "GW_Corr", "End_CorrRejected", name="رد"),
        Flow("Flow_Corr_Approve", "GW_Corr", "End_CorrApproved", name="تأیید", cond="action == 'approve'"),
    ]
    return build_bpmn("Definitions_Corr", "http://bpms.local/attendance",
                      "Process_AttendanceCorrection", "اصلاح تردد", nodes, flows), "Process_AttendanceCorrection"


def bpmn_documentation() -> tuple[str, str]:
    """۳) مستندسازی اسناد — ثبت، بازبینی کارشناس، تأیید نهایی و بایگانی."""
    nodes = [
        Node("Start_Doc", "startEvent", "شروع مستندسازی", 100, 232),
        Node("GW_Entry", "exclusiveGateway", "ادغام بازگشت‌ها", 190, 225),
        Node("Task_RegisterDoc", "userTask", "ثبت و ویرایش سند", 280, 210),
        Node("Task_ExpertReview", "userTask", "بازبینی کارشناس", 450, 210),
        Node("GW_Review", "exclusiveGateway", "نتیجه بازبینی", 620, 225, default_flow="Flow_DocRevise"),
        Node("End_DocRejected", "endEvent", "رد شده", 626, 350),
        Node("Task_FinalApproval", "userTask", "تأیید نهایی مدیر", 740, 210),
        Node("GW_Final", "exclusiveGateway", "تصمیم نهایی", 900, 225, default_flow="Flow_FinalRevise"),
        Node("Task_ArchiveDoc", "serviceTask", "بایگانی سند", 1000, 210),
        Node("End_DocArchived", "endEvent", "سند بایگانی شد", 1180, 232),
    ]
    flows = [
        Flow("F_Doc_Start", "Start_Doc", "GW_Entry"),
        Flow("F_Entry_Register", "GW_Entry", "Task_RegisterDoc"),
        Flow("F_Register_Review", "Task_RegisterDoc", "Task_ExpertReview"),
        Flow("F_Review_GW", "Task_ExpertReview", "GW_Review"),
        Flow("Flow_DocRevise", "GW_Review", "GW_Entry", name="اصلاح سند", cond="action == 'revision'"),
        Flow("Flow_DocReject", "GW_Review", "End_DocRejected", name="رد", cond="action == 'reject'"),
        Flow("Flow_DocApprove", "GW_Review", "Task_FinalApproval", name="تأیید", cond="action == 'approve'"),
        Flow("F_Final_GW", "Task_FinalApproval", "GW_Final"),
        Flow("Flow_FinalRevise", "GW_Final", "GW_Entry", name="بازگشت برای اصلاح", cond="action == 'revision'"),
        Flow("Flow_FinalApprove", "GW_Final", "Task_ArchiveDoc", name="تأیید نهایی", cond="action == 'approve'"),
        Flow("F_Archive_End", "Task_ArchiveDoc", "End_DocArchived"),
    ]
    return build_bpmn("Definitions_Doc", "http://bpms.local/docs",
                      "Process_Documentation", "مستندسازی اسناد سازمانی", nodes, flows), "Process_Documentation"


def bpmn_business_trip() -> tuple[str, str]:
    """۴) ماموریت اداری — تأیید مدیر، بررسی مالی برای هزینه بالا، صدور حکم و گزارش بازگشت."""
    nodes = [
        Node("Start_Trip", "startEvent", "ثبت درخواست ماموریت", 120, 252),
        Node("Task_TripRequest", "userTask", "تکمیل درخواست ماموریت", 200, 230),
        Node("Task_TripManager", "userTask", "تأیید مدیر", 370, 230),
        Node("GW_Trip", "exclusiveGateway", "تصمیم مدیر", 540, 245, default_flow="Flow_Trip_Reject"),
        Node("End_TripRejected", "endEvent", "رد شده", 546, 380),
        Node("GW_Cost", "exclusiveGateway", "بررسی سقف هزینه", 650, 245, default_flow="Flow_Cost_Low"),
        Node("Task_FinanceApprove", "userTask", "تأیید مالی", 730, 100),
        Node("GW_Fin", "exclusiveGateway", "تصمیم مالی", 920, 115, default_flow="Flow_Fin_Reject"),
        Node("GW_JoinOrder", "exclusiveGateway", "ادغام مسیرها", 860, 245),
        Node("Task_IssueOrder", "serviceTask", "صدور حکم ماموریت", 980, 230),
        Node("Task_TripReport", "userTask", "گزارش بازگشت از ماموریت", 1150, 230),
        Node("End_TripDone", "endEvent", "پایان ماموریت", 1330, 252),
    ]
    flows = [
        Flow("F_Trip_Start", "Start_Trip", "Task_TripRequest"),
        Flow("F_Trip_Req_Mgr", "Task_TripRequest", "Task_TripManager"),
        Flow("F_Trip_Mgr_GW", "Task_TripManager", "GW_Trip"),
        Flow("Flow_Trip_Reject", "GW_Trip", "End_TripRejected", name="رد"),
        Flow("Flow_Trip_Approve", "GW_Trip", "GW_Cost", name="تأیید", cond="action == 'approve'"),
        Flow("Flow_Cost_High", "GW_Cost", "Task_FinanceApprove", name="هزینه بالا", cond="trip_cost > 10000000"),
        Flow("Flow_Cost_Low", "GW_Cost", "GW_JoinOrder", name="هزینه معمولی"),
        Flow("F_Fin_GW", "Task_FinanceApprove", "GW_Fin"),
        Flow("Flow_Fin_Reject", "GW_Fin", "End_TripRejected", name="رد مالی"),
        Flow("Flow_Fin_Approve", "GW_Fin", "GW_JoinOrder", name="تأیید مالی", cond="action == 'approve'"),
        Flow("F_Join_Issue", "GW_JoinOrder", "Task_IssueOrder"),
        Flow("F_Issue_Report", "Task_IssueOrder", "Task_TripReport"),
        Flow("F_Report_End", "Task_TripReport", "End_TripDone"),
    ]
    return build_bpmn("Definitions_Trip", "http://bpms.local/mission",
                      "Process_BusinessTrip", "ماموریت اداری", nodes, flows), "Process_BusinessTrip"


def bpmn_it_ticket() -> tuple[str, str]:
    """۵) تیکت پشتیبانی IT — ثبت تیکت، بررسی، حل، تأیید درخواهنده و بستن."""
    nodes = [
        Node("Start_Ticket", "startEvent", "ثبت تیکت", 120, 252),
        Node("Task_CreateTicket", "userTask", "ثبت تیکت پشتیبانی", 200, 230),
        Node("GW_Merge", "exclusiveGateway", "ادغام بازگشت‌ها", 370, 245),
        Node("Task_Triage", "userTask", "بررسی و اولویت‌بندی", 450, 230),
        Node("Task_Solve", "userTask", "حل مشکل", 620, 230),
        Node("GW_Solved", "exclusiveGateway", "نتیجه حل", 790, 245, default_flow="Flow_Back_Triage"),
        Node("Task_Confirm", "userTask", "تأیید درخواهنده", 900, 230),
        Node("GW_Confirm", "exclusiveGateway", "نتیجه تأیید", 1070, 245, default_flow="Flow_Confirm_Back"),
        Node("End_TicketClosed", "endEvent", "تیکت بسته شد", 1160, 252),
    ]
    flows = [
        Flow("F_T_Start", "Start_Ticket", "Task_CreateTicket"),
        Flow("F_T_Create_Merge", "Task_CreateTicket", "GW_Merge"),
        Flow("F_Merge_Triage", "GW_Merge", "Task_Triage"),
        Flow("F_Triage_Solve", "Task_Triage", "Task_Solve"),
        Flow("F_Solve_GW", "Task_Solve", "GW_Solved"),
        Flow("Flow_Back_Triage", "GW_Solved", "GW_Merge", name="حل نشد — بررسی مجدد"),
        Flow("Flow_Solved", "GW_Solved", "Task_Confirm", name="حل شد", cond="action == 'solved'"),
        Flow("F_Confirm_GW", "Task_Confirm", "GW_Confirm"),
        Flow("Flow_Confirm_Back", "GW_Confirm", "GW_Merge", name="عدم تأیید"),
        Flow("Flow_Confirm_Close", "GW_Confirm", "End_TicketClosed", name="تأیید", cond="action == 'confirm'"),
    ]
    return build_bpmn("Definitions_Ticket", "http://bpms.local/it",
                      "Process_ItTicket", "تیکت پشتیبانی فناوری اطلاعات", nodes, flows), "Process_ItTicket"


# ============================== فرم‌ها ==============================

def schema_leave_request(leave_type_l, priority_l) -> dict:
    return {
        "title": "درخواست مرخصی",
        "theme": {"primary": "#059669", "headerBg": "linear-gradient(135deg,#059669,#047857)", "headerColor": "#ffffff",
                  "background": "#ecfdf5", "fieldBg": "#ffffff", "labelColor": "#064e3b", "radius": 10, "density": "comfortable"},
        "fields": [
            {"key": "sec_person", "type": "title", "label": "مشخصات متقاضی"},
            {"key": "full_name", "type": "text", "label": "نام و نام خانوادگی", "required": True, "colSpan": 8},
            {"key": "personnel_code", "type": "text", "label": "کد پرسنلی", "colSpan": 8},
            {"key": "unit_name", "type": "text", "label": "واحد سازمانی", "colSpan": 8},
            {"key": "sec_leave", "type": "title", "label": "مشخصات مرخصی"},
            {"key": "leave_type", "type": "select", "label": "نوع مرخصی", "required": True,
             "lookupId": leave_type_l.id if leave_type_l else None, "colSpan": 8},
            {"key": "from_date", "type": "jalali_date", "label": "از تاریخ", "required": True, "colSpan": 8},
            {"key": "to_date", "type": "jalali_date", "label": "تا تاریخ", "required": True, "colSpan": 8},
            {"key": "days_count", "type": "integer", "label": "تعداد روز", "required": True, "min": 1, "colSpan": 8},
            {"key": "deputy", "type": "user", "label": "جانشین در طول مرخصی", "colSpan": 8},
            {"key": "reason", "type": "textarea", "label": "دلیل مرخصی", "required": True, "colSpan": 24, "maxLength": 500},
        ],
    }


def schema_leave_decision() -> dict:
    return {
        "title": "تصمیم سرپرست",
        "fields": [
            {"key": "summary", "type": "summary", "label": "خلاصه درخواست"},
            {"key": "action", "type": "radio", "label": "تصمیم", "required": True, "colSpan": 24,
             "options": [{"value": "approve", "label": "تأیید"}, {"value": "reject", "label": "رد"}]},
            {"key": "comment", "type": "textarea", "label": "نظر", "colSpan": 24, "maxLength": 400},
        ],
    }


def schema_hr_decision() -> dict:
    return {
        "title": "تصمیم منابع انسانی",
        "fields": [
            {"key": "summary", "type": "summary", "label": "خلاصه درخواست"},
            {"key": "action", "type": "radio", "label": "تصمیم نهایی", "required": True, "colSpan": 24,
             "options": [{"value": "approve", "label": "تأیید"}, {"value": "reject", "label": "رد"}]},
            {"key": "hr_note", "type": "textarea", "label": "یادداشت منابع انسانی", "colSpan": 24},
        ],
    }


def schema_attendance_correction() -> dict:
    return {
        "title": "درخواست اصلاح تردد",
        "theme": {"primary": "#1d4ed8", "headerBg": "linear-gradient(135deg,#1d4ed8,#1e3a8a)", "headerColor": "#ffffff",
                  "background": "#eff6ff", "fieldBg": "#ffffff", "labelColor": "#172554", "radius": 8, "density": "comfortable"},
        "fields": [
            {"key": "full_name", "type": "text", "label": "نام و نام خانوادگی", "required": True, "colSpan": 8},
            {"key": "work_date", "type": "jalali_date", "label": "تاریخ تردد", "required": True, "colSpan": 8},
            {"key": "check_in", "type": "time", "label": "ساعت ورود واقعی", "colSpan": 8},
            {"key": "check_out", "type": "time", "label": "ساعت خروج واقعی", "colSpan": 8},
            {"key": "reason", "type": "textarea", "label": "دلیل مغایرت", "required": True, "colSpan": 24, "maxLength": 400},
        ],
    }


def schema_doc_register(doc_type_l) -> dict:
    return {
        "title": "ثبت سند سازمانی",
        "theme": {"primary": "#7c3aed", "headerBg": "linear-gradient(135deg,#7c3aed,#5b21b6)", "headerColor": "#ffffff",
                  "background": "#f5f3ff", "fieldBg": "#ffffff", "labelColor": "#2e1065", "radius": 12, "density": "comfortable"},
        "fields": [
            {"key": "doc_title", "type": "text", "label": "عنوان سند", "required": True, "colSpan": 16},
            {"key": "doc_type", "type": "select", "label": "نوع سند", "required": True,
             "lookupId": doc_type_l.id if doc_type_l else None, "colSpan": 8},
            {"key": "doc_version", "type": "text", "label": "نسخه", "colSpan": 8, "help": "مثال: 1.0"},
            {"key": "doc_owner", "type": "text", "label": "مالک سند (واحد)", "colSpan": 8},
            {"key": "summary", "type": "textarea", "label": "خلاصه سند", "colSpan": 24, "maxLength": 800},
            {"key": "attachment", "type": "file", "label": "فایل سند", "colSpan": 24},
        ],
    }


def schema_doc_review() -> dict:
    return {
        "title": "بازبینی سند",
        "fields": [
            {"key": "summary", "type": "summary", "label": "خلاصه سند"},
            {"key": "action", "type": "radio", "label": "نتیجه بازبینی", "required": True, "colSpan": 24,
             "options": [{"value": "approve", "label": "تأیید"}, {"value": "revision", "label": "نیاز به اصلاح"}, {"value": "reject", "label": "رد"}]},
            {"key": "review_comment", "type": "textarea", "label": "نظرات اصلاحی", "colSpan": 24, "maxLength": 600},
        ],
    }


def schema_doc_final() -> dict:
    return {
        "title": "تأیید نهایی سند",
        "fields": [
            {"key": "summary", "type": "summary", "label": "خلاصه سند"},
            {"key": "action", "type": "radio", "label": "تصمیم نهایی", "required": True, "colSpan": 24,
             "options": [{"value": "approve", "label": "تأیید نهایی"}, {"value": "revision", "label": "بازگشت برای اصلاح"}]},
            {"key": "final_note", "type": "textarea", "label": "یادداشت", "colSpan": 24},
        ],
    }


def schema_trip_request() -> dict:
    return {
        "title": "درخواست ماموریت اداری",
        "theme": {"primary": "#d97706", "headerBg": "linear-gradient(135deg,#d97706,#b45309)", "headerColor": "#ffffff",
                  "background": "#fffbeb", "fieldBg": "#ffffff", "labelColor": "#451a03", "radius": 10, "density": "comfortable"},
        "fields": [
            {"key": "sec_person", "type": "title", "label": "مشخصات مامور"},
            {"key": "full_name", "type": "text", "label": "نام و نام خانوادگی", "required": True, "colSpan": 8},
            {"key": "unit_name", "type": "text", "label": "واحد سازمانی", "colSpan": 8},
            {"key": "destination", "type": "text", "label": "مقصد ماموریت", "required": True, "colSpan": 8},
            {"key": "sec_trip", "type": "title", "label": "جزئیات ماموریت"},
            {"key": "from_date", "type": "jalali_date", "label": "تاریخ رفت", "required": True, "colSpan": 8},
            {"key": "to_date", "type": "jalali_date", "label": "تاریخ برگشت", "required": True, "colSpan": 8},
            {"key": "trip_cost", "type": "money", "label": "برآورد هزینه (ریال)", "required": True, "min": 0, "moneyUnit": "ریال", "colSpan": 8},
            {"key": "purpose", "type": "textarea", "label": "هدف ماموریت", "required": True, "colSpan": 24, "maxLength": 500},
        ],
    }


def schema_trip_decision() -> dict:
    return {
        "title": "تصمیم درباره ماموریت",
        "fields": [
            {"key": "summary", "type": "summary", "label": "خلاصه درخواست"},
            {"key": "action", "type": "radio", "label": "تصمیم", "required": True, "colSpan": 24,
             "options": [{"value": "approve", "label": "تأیید"}, {"value": "reject", "label": "رد"}]},
            {"key": "comment", "type": "textarea", "label": "نظر", "colSpan": 24},
        ],
    }


def schema_trip_report() -> dict:
    return {
        "title": "گزارش بازگشت از ماموریت",
        "fields": [
            {"key": "summary", "type": "summary", "label": "خلاصه ماموریت"},
            {"key": "trip_report", "type": "textarea", "label": "شرح نتایج ماموریت", "required": True, "colSpan": 24, "maxLength": 1000},
            {"key": "actual_cost", "type": "money", "label": "هزینه واقعی (ریال)", "moneyUnit": "ریال", "colSpan": 12},
        ],
    }


def schema_ticket(ticket_cat_l, priority_l) -> dict:
    return {
        "title": "ثبت تیکت پشتیبانی",
        "theme": {"primary": "#0e7490", "headerBg": "linear-gradient(135deg,#0e7490,#155e75)", "headerColor": "#ffffff",
                  "background": "#ecfeff", "fieldBg": "#ffffff", "labelColor": "#083344", "radius": 8, "density": "compact"},
        "fields": [
            {"key": "ticket_title", "type": "text", "label": "عنوان تیکت", "required": True, "colSpan": 16},
            {"key": "ticket_category", "type": "select", "label": "دسته‌بندی", "required": True,
             "lookupId": ticket_cat_l.id if ticket_cat_l else None, "colSpan": 8},
            {"key": "priority", "type": "select", "label": "اهمیت", "lookupId": priority_l.id if priority_l else None, "colSpan": 8},
            {"key": "description", "type": "textarea", "label": "شرح مشکل", "required": True, "colSpan": 24, "maxLength": 1000},
            {"key": "attachment", "type": "file", "label": "تصویر/فایل مشکل", "colSpan": 24},
        ],
    }


def schema_ticket_solution() -> dict:
    return {
        "title": "بررسی و حل تیکت",
        "fields": [
            {"key": "summary", "type": "summary", "label": "خلاصه تیکت"},
            {"key": "action", "type": "radio", "label": "نتیجه", "required": True, "colSpan": 24,
             "options": [{"value": "solved", "label": "حل شد"}, {"value": "return", "label": "نیاز به بررسی مجدد"}]},
            {"key": "solution", "type": "textarea", "label": "شرح راه‌حل", "colSpan": 24, "maxLength": 800},
        ],
    }


def schema_ticket_confirm() -> dict:
    return {
        "title": "تأیید درخواهنده",
        "fields": [
            {"key": "summary", "type": "summary", "label": "خلاصه تیکت"},
            {"key": "action", "type": "radio", "label": "آیا مشکل حل شده است؟", "required": True, "colSpan": 24,
             "options": [{"value": "confirm", "label": "بله، تأیید"}, {"value": "return", "label": "خیر — بازگشت"}]},
            {"key": "satisfaction", "type": "radio", "label": "میزان رضایت", "colSpan": 24,
             "options": [{"value": "high", "label": "عالی"}, {"value": "mid", "label": "خوب"}, {"value": "low", "label": "ضعیف"}]},
        ],
    }


# ============================== اجرای Seed ==============================

def seed_samples():
    # ساخت جدول‌های بانک سازمانی اگر مایگریشن/seed قبلی اجرا نشده باشد
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # ---------- نقش‌ها و کاربران نمونه ----------
        extra_roles = {
            "hr": ("کارشناس منابع انسانی", ["task.claim", "task.complete", "process.view"]),
            "it_support": ("کارشناس پشتیبانی فناوری اطلاعات", ["task.claim", "task.complete", "process.view"]),
        }
        roles = {}
        for code, (title, perms) in extra_roles.items():
            r = db.scalar(select(Role).where(Role.code == code))
            if not r:
                r = Role(code=code, title=title, permissions=perms)
                db.add(r)
            else:
                r.title, r.permissions = title, perms
            roles[code] = r
        db.flush()

        extra_users = [
            ("hr1", "کارشناس منابع انسانی (زهرا احمدی)", ["hr"]),
            ("it1", "کارشناس پشتیبانی فناوری اطلاعات (مهدی نوری)", ["it_support"]),
        ]
        users = {}
        for username, full_name, role_codes in extra_users:
            u = db.scalar(select(User).where(User.username == username))
            if not u:
                u = User(username=username, password_hash=hash_password(DEFAULT_PASSWORD),
                         full_name=full_name, is_superadmin=False)
                db.add(u)
                db.flush()
                for rc in role_codes:
                    u.roles.append(roles[rc])
            users[username] = u

        # ---------- واحدهای سازمانی تکمیلی ----------
        hq = db.scalar(select(OrganizationUnit).where(OrganizationUnit.code == "HQ"))
        if hq and not db.scalar(select(OrganizationUnit).where(OrganizationUnit.code == "HR_UNIT")):
            db.add(OrganizationUnit(name="واحد منابع انسانی", code="HR_UNIT", parent=hq))
        if hq and not db.scalar(select(OrganizationUnit).where(OrganizationUnit.code == "DOC_OFFICE")):
            db.add(OrganizationUnit(name="دفتر اسناد و مدارک", code="DOC_OFFICE", parent=hq))
        db.flush()

        # ---------- جداول پایه تکمیلی ----------
        def lookup(key, title, items):
            l = db.scalar(select(LookupDefinition).where(LookupDefinition.key == key))
            if not l:
                l = LookupDefinition(key=key, title=title)
                db.add(l)
                db.flush()
            if not l.items:
                for code, lbl, parent_code in items:
                    db.add(LookupItem(lookup_id=l.id, code=code, title=lbl, parent_id=None))
                db.flush()
            return l

        leave_type_l = lookup("leave_type", "نوع مرخصی", [
            ("earned", "استحقاقی", None), ("sick", "استعلاجی", None), ("hourly", "ساعتی", None),
            ("unpaid", "بدون حقوق", None), ("maternity", "زایمان", None)])
        doc_type_l = lookup("doc_type", "نوع سند", [
            ("bylaw", "آیین‌نامه", None), ("procedure", "رویه", None),
            ("instruction", "دستورالعمل", None), ("form", "فرم", None)])
        ticket_cat_l = lookup("ticket_category", "دسته تیکت", [
            ("hardware", "سخت‌افزار", None), ("software", "نرم‌افزار", None),
            ("network", "شبکه", None), ("account", "حساب کاربری", None), ("other", "سایر", None)])
        priority_l = db.scalar(select(LookupDefinition).where(LookupDefinition.key == "priority"))
        db.flush()

        # ---------- فیلدهای سازمانی بانک ----------
        org_fields = [
            ("personnel_code", "کد پرسنلی", "text", "پرسنلی", {"required": True, "help": "کد یکتای پرسنلی کارمند"}),
            ("work_email", "ایمیل سازمانی", "email", "پرسنلی", {}),
            ("emergency_mobile", "موبایل اضطراری", "mobile", "پرسنلی", {}),
            ("employment_date", "تاریخ استخدام", "jalali_date", "پرسنلی", {}),
            ("shaba_number", "شماره شبا", "text", "مالی", {"help": "IR به‌همراه ۲۴ رقم"}),
            ("bank_account", "شماره حساب", "text", "مالی", {}),
        ]
        for key, label, ftype, cat, cfg in org_fields:
            if not db.scalar(select(OrgField).where(OrgField.key == key)):
                db.add(OrgField(key=key, label=label, type=ftype, category=cat,
                                config_json=cfg, created_by_id=users["hr1"].id))
        db.flush()

        # ---------- فرم‌های نمونه ----------
        def make_form(key, title, schema, publish=True):
            f = db.scalar(select(FormDefinition).where(FormDefinition.key == key))
            if not f:
                f = FormDefinition(key=key, title=title, created_by_id=users["hr1"].id)
                db.add(f)
                db.flush()
            if not f.versions:
                v = FormVersion(form_id=f.id, version=1, schema_json=schema,
                                created_by_id=users["hr1"].id, change_note="نسخه اولیه نمونه")
                if publish:
                    v.status = "published"
                    v.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.add(v)
                db.flush()
            return f

        f_leave = make_form("leave_request", "درخواست مرخصی", schema_leave_request(leave_type_l, priority_l))
        f_leave_decision = make_form("leave_decision", "تصمیم سرپرست (مرخصی)", schema_leave_decision())
        f_hr_decision = make_form("hr_decision", "تصمیم منابع انسانی", schema_hr_decision())
        f_corr = make_form("attendance_correction", "اصلاح تردد", schema_attendance_correction())
        f_doc_register = make_form("doc_register", "ثبت سند سازمانی", schema_doc_register(doc_type_l))
        f_doc_review = make_form("doc_review", "بازبینی سند", schema_doc_review())
        f_doc_final = make_form("doc_final", "تأیید نهایی سند", schema_doc_final())
        f_trip = make_form("trip_request", "درخواست ماموریت اداری", schema_trip_request())
        f_trip_decision = make_form("trip_decision", "تصمیم ماموریت", schema_trip_decision())
        f_trip_report = make_form("trip_report", "گزارش بازگشت ماموریت", schema_trip_report())
        f_ticket = make_form("it_ticket", "تیکت پشتیبانی", schema_ticket(ticket_cat_l, priority_l))
        f_ticket_solution = make_form("it_ticket_solution", "حل تیکت", schema_ticket_solution())
        f_ticket_confirm = make_form("it_ticket_confirm", "تأیید درخواهنده", schema_ticket_confirm())

        # ---------- فرایندهای نمونه ----------
        def make_process(key, title, desc, xml, main_pid, bindings, publisher_role="manager"):
            p = db.scalar(select(ProcessDefinition).where(ProcessDefinition.key == key))
            if not p:
                p = ProcessDefinition(key=key, title=title, description=desc, created_by_id=users["hr1"].id)
                db.add(p)
                db.flush()
            if not p.versions:
                v = ProcessVersion(definition_id=p.id, version=1, bpmn_xml=xml,
                                   main_process_id=main_pid, config_json={"bindings": bindings},
                                   created_by_id=users["hr1"].id, change_note="نمونه آماده فاز ۸",
                                   status="published")
                v.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.add(v)
            return p

        xml_leave, pid_leave = bpmn_leave_request()
        make_process("leave_request", "مرخصی کارکنان",
                     "ثبت مرخصی، تأیید سرپرست و ارجاع به منابع انسانی برای بیش از ۳ روز",
                     xml_leave, pid_leave, {
                         "Start_Leave": {"formDefinitionId": f_leave.id},
                         "Task_SubmitLeave": {"formDefinitionId": f_leave.id, "assigneeType": "field", "assigneeValue": "_initiator_id"},
                         "Task_SupervisorApprove": {"formDefinitionId": f_leave_decision.id, "assigneeType": "role", "assigneeValue": "manager",
                                                    "results": [{"value": "approve", "label": "تأیید"}, {"value": "reject", "label": "رد"}], "dueHours": 24},
                         "Task_HRApprove": {"formDefinitionId": f_hr_decision.id, "assigneeType": "role", "assigneeValue": "hr",
                                            "results": [{"value": "approve", "label": "تأیید"}, {"value": "reject", "label": "رد"}], "dueHours": 48},
                     })

        xml_corr, pid_corr = bpmn_attendance_correction()
        make_process("attendance_correction", "اصلاح تردد",
                     "ثبت مغایرت ورود/خروج و بررسی سرپرست",
                     xml_corr, pid_corr, {
                         "Start_Corr": {"formDefinitionId": f_corr.id},
                         "Task_SubmitCorr": {"formDefinitionId": f_corr.id, "assigneeType": "field", "assigneeValue": "_initiator_id"},
                         "Task_SupervisorCheck": {"formDefinitionId": f_leave_decision.id, "assigneeType": "role", "assigneeValue": "manager",
                                                  "results": [{"value": "approve", "label": "تأیید"}, {"value": "reject", "label": "رد"}], "dueHours": 24},
                     })

        xml_doc, pid_doc = bpmn_documentation()
        make_process("documentation", "مستندسازی اسناد سازمانی",
                     "ثبت سند، بازبینی کارشناس، تأیید نهایی مدیر و بایگانی",
                     xml_doc, pid_doc, {
                         "Start_Doc": {"formDefinitionId": f_doc_register.id},
                         "Task_RegisterDoc": {"formDefinitionId": f_doc_register.id, "assigneeType": "field", "assigneeValue": "_initiator_id"},
                         "Task_ExpertReview": {"formDefinitionId": f_doc_review.id, "assigneeType": "role", "assigneeValue": "manager",
                                               "results": [{"value": "approve", "label": "تأیید"}, {"value": "revision", "label": "نیاز به اصلاح"}, {"value": "reject", "label": "رد"}], "dueHours": 48},
                         "Task_FinalApproval": {"formDefinitionId": f_doc_final.id, "assigneeType": "role", "assigneeValue": "manager",
                                                "results": [{"value": "approve", "label": "تأیید نهایی"}, {"value": "revision", "label": "بازگشت"}], "dueHours": 48},
                         "Task_ArchiveDoc": {"connector": "mock:archive_document"},
                     })

        xml_trip, pid_trip = bpmn_business_trip()
        make_process("business_trip", "ماموریت اداری",
                     "تأیید مدیر، بررسی مالی مبلغ‌های بالا، صدور حکم و گزارش بازگشت",
                     xml_trip, pid_trip, {
                         "Start_Trip": {"formDefinitionId": f_trip.id},
                         "Task_TripRequest": {"formDefinitionId": f_trip.id, "assigneeType": "field", "assigneeValue": "_initiator_id"},
                         "Task_TripManager": {"formDefinitionId": f_trip_decision.id, "assigneeType": "role", "assigneeValue": "manager",
                                              "results": [{"value": "approve", "label": "تأیید"}, {"value": "reject", "label": "رد"}], "dueHours": 24},
                         "Task_FinanceApprove": {"formDefinitionId": f_trip_decision.id, "assigneeType": "role", "assigneeValue": "finance",
                                                 "results": [{"value": "approve", "label": "تأیید مالی"}, {"value": "reject", "label": "رد"}], "dueHours": 48},
                         "Task_IssueOrder": {"connector": "mock:issue_mission_order"},
                         "Task_TripReport": {"formDefinitionId": f_trip_report.id, "assigneeType": "field", "assigneeValue": "_initiator_id"},
                     })

        xml_ticket, pid_ticket = bpmn_it_ticket()
        make_process("it_ticket", "تیکت پشتیبانی فناوری اطلاعات",
                     "ثبت تیکت، بررسی، حل مشکل، تأیید درخواهنده و بستن تیکت",
                     xml_ticket, pid_ticket, {
                         "Start_Ticket": {"formDefinitionId": f_ticket.id},
                         "Task_CreateTicket": {"formDefinitionId": f_ticket.id, "assigneeType": "field", "assigneeValue": "_initiator_id"},
                         "Task_Triage": {"formDefinitionId": f_ticket_solution.id, "assigneeType": "role", "assigneeValue": "it_support",
                                         "results": [{"value": "solved", "label": "حل شد"}, {"value": "return", "label": "بررسی مجدد"}], "dueHours": 8},
                         "Task_Solve": {"formDefinitionId": f_ticket_solution.id, "assigneeType": "role", "assigneeValue": "it_support",
                                        "results": [{"value": "solved", "label": "حل شد"}, {"value": "return", "label": "بررسی مجدد"}], "dueHours": 24},
                         "Task_Confirm": {"formDefinitionId": f_ticket_confirm.id, "assigneeType": "field", "assigneeValue": "_initiator_id",
                                          "results": [{"value": "confirm", "label": "تأیید"}, {"value": "return", "label": "بازگشت"}], "dueHours": 48},
                     })

        # ---------- بانک سازمانی: الگوی فرم‌ها و فرایندها ----------
        def form_tpl(key, title, desc, category, schema):
            if not db.scalar(select(FormTemplate).where(FormTemplate.key == key)):
                db.add(FormTemplate(key=key, title=title, description=desc, category=category,
                                    schema_json=schema, created_by_id=users["hr1"].id))

        form_tpl("tpl_leave_request", "الگو: درخواست مرخصی", "فرم استاندارد مرخصی کارکنان با تم سبز", "منابع انسانی",
                 schema_leave_request(leave_type_l, priority_l))
        form_tpl("tpl_doc_register", "الگو: ثبت سند سازمانی", "فرم مستندسازی با پیوست", "مستندسازی",
                 schema_doc_register(doc_type_l))
        form_tpl("tpl_it_ticket", "الگو: تیکت پشتیبانی", "فرم تیکت با دسته‌بندی و پیوست", "پشتیبانی",
                 schema_ticket(ticket_cat_l, priority_l))
        form_tpl("tpl_trip_request", "الگو: ماموریت اداری", "فرم ماموریت با برآورد هزینه", "اداری",
                 schema_trip_request())
        db.flush()

        def proc_tpl(key, title, desc, category, xml, main_pid, bindings):
            if not db.scalar(select(ProcessTemplate).where(ProcessTemplate.key == key)):
                db.add(ProcessTemplate(key=key, title=title, description=desc, category=category,
                                       bpmn_xml=xml, main_process_id=main_pid,
                                       config_json={"bindings": bindings}, created_by_id=users["hr1"].id))

        proc_tpl("tpl_process_leave", "الگو: فرایند مرخصی", "با ارجاع شرطی به منابع انسانی", "منابع انسانی",
                 xml_leave, pid_leave, {
                     "Task_SubmitLeave": {"formDefinitionId": f_leave.id, "assigneeType": "field", "assigneeValue": "_initiator_id"},
                     "Task_SupervisorApprove": {"formDefinitionId": f_leave_decision.id, "assigneeType": "role", "assigneeValue": "manager"},
                     "Task_HRApprove": {"formDefinitionId": f_hr_decision.id, "assigneeType": "role", "assigneeValue": "hr"},
                 })
        proc_tpl("tpl_process_documentation", "الگو: فرایند مستندسازی", "چرخه کامل سند تا بایگانی", "مستندسازی",
                 xml_doc, pid_doc, {
                     "Task_RegisterDoc": {"formDefinitionId": f_doc_register.id, "assigneeType": "field", "assigneeValue": "_initiator_id"},
                     "Task_ExpertReview": {"formDefinitionId": f_doc_review.id, "assigneeType": "role", "assigneeValue": "manager"},
                     "Task_FinalApproval": {"formDefinitionId": f_doc_final.id, "assigneeType": "role", "assigneeValue": "manager"},
                     "Task_ArchiveDoc": {"connector": "mock:archive_document"},
                 })
        proc_tpl("tpl_process_it_ticket", "الگو: فرایند تیکت پشتیبانی", "حلقه حل و تأیید درخواهنده", "پشتیبانی",
                 xml_ticket, pid_ticket, {
                     "Task_CreateTicket": {"formDefinitionId": f_ticket.id, "assigneeType": "field", "assigneeValue": "_initiator_id"},
                     "Task_Triage": {"formDefinitionId": f_ticket_solution.id, "assigneeType": "role", "assigneeValue": "it_support"},
                     "Task_Solve": {"formDefinitionId": f_ticket_solution.id, "assigneeType": "role", "assigneeValue": "it_support"},
                     "Task_Confirm": {"formDefinitionId": f_ticket_confirm.id, "assigneeType": "field", "assigneeValue": "_initiator_id"},
                 })
        proc_tpl("tpl_process_trip", "الگو: فرایند ماموریت اداری", "با سقف هزینه و تأیید مالی", "اداری",
                 xml_trip, pid_trip, {
                     "Task_TripRequest": {"formDefinitionId": f_trip.id, "assigneeType": "field", "assigneeValue": "_initiator_id"},
                     "Task_TripManager": {"formDefinitionId": f_trip_decision.id, "assigneeType": "role", "assigneeValue": "manager"},
                     "Task_FinanceApprove": {"formDefinitionId": f_trip_decision.id, "assigneeType": "role", "assigneeValue": "finance"},
                     "Task_TripReport": {"formDefinitionId": f_trip_report.id, "assigneeType": "field", "assigneeValue": "_initiator_id"},
                 })

        # ---------- ذخیره فایل‌های BPMN در پوشه داده ----------
        os.makedirs(BPMN_DIR, exist_ok=True)
        for fname, xml in [
            ("leave_request.bpmn", xml_leave),
            ("attendance_correction.bpmn", xml_corr),
            ("documentation.bpmn", xml_doc),
            ("business_trip.bpmn", xml_trip),
            ("it_ticket.bpmn", xml_ticket),
        ]:
            with open(os.path.join(BPMN_DIR, fname), "w", encoding="utf-8") as fh:
                fh.write(xml)

        db.commit()
        print("✅ نمونه‌پروژه‌ها ثبت شدند: مرخصی، اصلاح تردد، مستندسازی، ماموریت اداری، تیکت پشتیبانی")
        print("   کاربران جدید (گذرواژه همه:", DEFAULT_PASSWORD, "): hr1 (منابع انسانی)، it1 (پشتیبانی فناوری)")
        print("   بانک سازمانی: ۶ فیلد سازمانی + ۴ الگوی فرم + ۴ الگوی فرایند")
    finally:
        db.close()


if __name__ == "__main__":
    seed_samples()
