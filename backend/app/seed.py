# -*- coding: utf-8 -*-
"""داده اولیه سامانه: نقش‌ها، کاربران نمونه، جداول پایه، فرم‌ها و فرایند «درخواست خرید».

اجرا: python -m app.seed
سناریوی §۳۵ سند باید با این داده‌ها از ابتدا تا انتها قابل اجرا باشد.
"""
import json
from datetime import datetime, timezone, date

from sqlalchemy import select

from app.core.database import SessionLocal, Base, engine
from app.core.security import hash_password
from app.modules.identity.models import Role, User
from app.modules.organization.models import OrganizationUnit
from app.modules.lookups.router import LookupDefinition, LookupItem
from app.modules.forms.models import FormDefinition, FormVersion
from app.modules.engine.models import ProcessDefinition, ProcessVersion
from app.modules.decisions.models import DecisionDefinition, DecisionVersion
from app.modules.calendars.models import WorkCalendar, CalendarHoliday
from app.modules.identity.router import ALL_PERMISSIONS

DEFAULT_PASSWORD = "Bpms@1234"

# برنامه هفتگی تقویم کاری پیش‌فرض — شنبه تا چهارشنبه ۸–۱۶ با وقفه ناهار، پنجشنبه ۸–۱۲
DEFAULT_SCHEDULE = {
    "saturday":  {"enabled": True, "start": "08:00", "end": "16:00", "breaks": [{"start": "12:00", "end": "13:00"}]},
    "sunday":    {"enabled": True, "start": "08:00", "end": "16:00", "breaks": [{"start": "12:00", "end": "13:00"}]},
    "monday":    {"enabled": True, "start": "08:00", "end": "16:00", "breaks": [{"start": "12:00", "end": "13:00"}]},
    "tuesday":   {"enabled": True, "start": "08:00", "end": "16:00", "breaks": [{"start": "12:00", "end": "13:00"}]},
    "wednesday": {"enabled": True, "start": "08:00", "end": "16:00", "breaks": [{"start": "12:00", "end": "13:00"}]},
    "thursday":  {"enabled": True, "start": "08:00", "end": "12:00", "breaks": []},
    "friday":    {"enabled": False, "start": "08:00", "end": "16:00", "breaks": []},
}

# جدول تصمیم نمونه — سطح‌بندی تأیید خرید بر اساس مبلغ و اولویت
PURCHASE_DECISION_SCHEMA = {
    "hitPolicy": "FIRST",
    "inputs": [
        {"name": "total_amount", "label": "مبلغ کل (ریال)", "type": "number"},
        {"name": "priority", "label": "اولویت", "type": "string"},
    ],
    "outputs": [
        {"name": "approval_level", "label": "سطح تأیید", "defaultValue": "manager"},
        {"name": "needs_finance_review", "label": "بررسی مالی", "defaultValue": True},
    ],
    "rules": [
        {"id": "r1", "label": "خرید فوری با مبلغ بیش از ۱۰ میلیون",
         "inputEntries": {"total_amount": "> 10000000", "priority": "high"},
         "outputEntries": {"approval_level": "director", "needs_finance_review": True},
         "priority": 1, "enabled": True},
        {"id": "r2", "label": "مبلغ بیش از ۵۰ میلیون",
         "inputEntries": {"total_amount": "> 50000000", "priority": "-"},
         "outputEntries": {"approval_level": "director", "needs_finance_review": True},
         "priority": 2, "enabled": True},
        {"id": "r3", "label": "مبلغ ۱۰ تا ۵۰ میلیون",
         "inputEntries": {"total_amount": "between 10000000..50000000", "priority": "-"},
         "outputEntries": {"approval_level": "manager", "needs_finance_review": True},
         "priority": 3, "enabled": True},
        {"id": "r4", "label": "خرید خرد",
         "inputEntries": {"total_amount": "<= 10000000", "priority": "-"},
         "outputEntries": {"approval_level": "manager", "needs_finance_review": False},
         "priority": 4, "enabled": True},
    ],
}


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # ---------- نقش‌ها ----------
        roles_spec = {
            "admin": ("مدیر سامانه", ["*"]),
            "process_designer": ("طراح فرایند", ["process.view", "process.manage", "form.view", "monitor.view", "decision.view", "decision.manage", "calendar.view"]),
            "form_designer": ("طراح فرم", ["form.view", "form.manage"]),
            "publisher": ("مسئول انتشار", ["process.view", "process.publish", "form.view", "form.publish", "decision.view"]),
            "base_data_admin": ("مدیر داده‌های پایه", ["lookup.manage", "form.view", "calendar.manage", "calendar.view"]),
            "manager": ("مدیر واحد", ["task.claim", "task.complete", "process.start", "process.view", "monitor.view", "report.view"]),
            "finance": ("کارشناس مالی", ["task.claim", "task.complete", "process.view"]),
            "operator": ("کاربر اجرایی", ["process.start", "task.claim", "task.complete"]),
            "monitor": ("ناظر فرایند", ["monitor.view", "process.view", "report.view"]),
            "auditor": ("حسابرس", ["audit.view", "monitor.view", "report.view"]),
        }
        roles = {}
        for code, (title, perms) in roles_spec.items():
            r = db.scalar(select(Role).where(Role.code == code))
            if not r:
                r = Role(code=code, title=title, permissions=sorted(set(perms)))
                db.add(r)
            else:
                r.title, r.permissions = title, sorted(set(perms))
            roles[code] = r
        db.flush()

        # ---------- ساختار سازمانی ----------
        def unit(name, code, parent=None):
            u = OrganizationUnit(name=name, code=code, parent=parent)
            db.add(u)
            db.flush()
            return u

        if not db.scalar(select(OrganizationUnit).limit(1)):
            it = unit("شرکت نمونه", "HQ")
            it_dev = unit("معاونت توسعه", "DEV", it)
            it_fin = unit("معاونت مالی", "FIN", it)
            unit("واحد فناوری اطلاعات", "IT", it_dev)
            unit("واحد تدارکات", "PROC", it_fin)
            unit("واحد مالی", "ACC", it_fin)

        # ---------- کاربران ----------
        users_spec = [
            ("admin", "مدیر سامانه", ["admin"], True),
            ("designer", "طراح فرایند", ["process_designer"], False),
            ("formdesigner", "طراح فرم", ["form_designer"], False),
            ("publisher", "مسئول انتشار", ["publisher"], False),
            ("basedata", "مدیر داده پایه", ["base_data_admin"], False),
            ("manager", "مدیر واحد (سعید محمدی)", ["manager"], False),
            ("finance1", "کارشناس مالی (مریم کریمی)", ["finance"], False),
            ("user1", "کاربر اجرایی (علی رضایی)", ["operator"], False),
            ("monitor1", "ناظر فرایند", ["monitor"], False),
            ("auditor1", "حسابرس", ["auditor"], False),
        ]
        users = {}
        for username, full_name, role_codes, is_super in users_spec:
            u = db.scalar(select(User).where(User.username == username))
            if not u:
                u = User(username=username, password_hash=hash_password(DEFAULT_PASSWORD),
                         full_name=full_name, is_superadmin=is_super)
                db.add(u)
                db.flush()
                for rc in role_codes:
                    u.roles.append(roles[rc])
            users[username] = u

        # ---------- جداول پایه ----------
        def lookup(key, title, items, tree=False):
            l = db.scalar(select(LookupDefinition).where(LookupDefinition.key == key))
            if not l:
                l = LookupDefinition(key=key, title=title)
                db.add(l)
                db.flush()
            if not l.items:
                parents = {}
                for code, lbl, parent_code in items:
                    it = LookupItem(lookup_id=l.id, code=code, title=lbl,
                                    parent_id=parents.get(parent_code) if parent_code else None)
                    db.add(it)
                    db.flush()
                    parents[code] = it.id
            return l

        lookup("request_type", "نوع درخواست", [
            ("goods", "کالا", None), ("service", "خدمات", None), ("repair", "تعمیر و نگهداری", None)])
        lookup("priority", "اولویت", [
            ("low", "کم", None), ("normal", "متوسط", None), ("high", "فوری", None)])
        lookup("province", "استان", [
            ("tehran", "تهران", None), ("isfahan", "اصفهان", None), ("khorasan", "خراسان رضوی", None)])
        lookup("city", "شهر", [
            ("tehran_city", "تهران", "tehran"), ("islamic_shahr", "اسلامشهر", "tehran"),
            ("isfahan_city", "اصفهان", "isfahan"), ("kashan", "کاشان", "isfahan"),
            ("mashhad", "مشهد", "khorasan"), ("neyshabur", "نیشابور", "khorasan")])
        province_l = db.scalar(select(LookupDefinition).where(LookupDefinition.key == "province"))
        city_l = db.scalar(select(LookupDefinition).where(LookupDefinition.key == "city"))
        req_type_l = db.scalar(select(LookupDefinition).where(LookupDefinition.key == "request_type"))
        priority_l = db.scalar(select(LookupDefinition).where(LookupDefinition.key == "priority"))
        db.flush()

        # ---------- تقویم کاری پیش‌فرض (فاز ۳) ----------
        cal = db.scalar(select(WorkCalendar).where(WorkCalendar.is_default.is_(True)))
        if not cal:
            cal = WorkCalendar(name="تقویم کاری پیش‌فرض",
                               description="شنبه تا چهارشنبه ۸ تا ۱۶ (وقفه ناهار ۱۲–۱۳)، پنجشنبه ۸ تا ۱۲، جمعه تعطیل",
                               timezone="Asia/Tehran", schedule_json=DEFAULT_SCHEDULE, is_default=True,
                               created_by_id=users["basedata"].id)
            db.add(cal)
            db.flush()
            # نمونه تعطیلی تکرارشونده سالانه — نوروز
            db.add(CalendarHoliday(calendar_id=cal.id, date=date(2026, 3, 21),
                                    title="نوروز", yearly=True))

        # ---------- جدول تصمیم نمونه (فاز ۳) ----------
        dd = db.scalar(select(DecisionDefinition).where(DecisionDefinition.key == "purchase_approval"))
        if not dd:
            dd = DecisionDefinition(key="purchase_approval", title="سطح‌بندی تأیید خرید",
                                    description="تصمیم‌گیری بر اساس مبلغ و اولویت (DMN سبک فاز ۳)",
                                    created_by_id=users["designer"].id)
            db.add(dd)
            db.flush()
            dv = DecisionVersion(definition_id=dd.id, version=1, schema_json=PURCHASE_DECISION_SCHEMA,
                                 created_by_id=users["designer"].id, change_note="نسخه اولیه",
                                 status="published")
            dv.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.add(dv)

        # ---------- فرم‌ها ----------
        def make_form(key, title, schema, publish=True):
            f = db.scalar(select(FormDefinition).where(FormDefinition.key == key))
            if not f:
                f = FormDefinition(key=key, title=title, created_by_id=users["formdesigner"].id)
                db.add(f)
                db.flush()
            if not f.versions:
                v = FormVersion(form_id=f.id, version=1, schema_json=schema,
                                created_by_id=users["formdesigner"].id, change_note="نسخه اولیه")
                if publish:
                    v.status = "published"
                    v.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    v.published_by_id = users["admin"].id
                db.add(v)
                db.flush()
            return f

        f_requester_info = make_form("requester_info", "مشخصات درخواست‌دهنده", {
            "title": "مشخصات درخواست‌دهنده",
            "fields": [
                {"key": "full_name", "type": "text", "label": "نام و نام خانوادگی", "required": True, "colSpan": 8},
                {"key": "national_id", "type": "national_id", "label": "کد ملی", "required": True, "colSpan": 8},
                {"key": "mobile", "type": "mobile", "label": "شماره موبایل", "required": True, "colSpan": 8},
                {"key": "birth_date", "type": "jalali_date", "label": "تاریخ تولد", "colSpan": 8},
                {"key": "address", "type": "textarea", "label": "نشانی", "colSpan": 24, "maxLength": 500},
            ],
        })

        f_purchase_item = make_form("purchase_item", "اقلام درخواست خرید (ردیف)", {
            "title": "ردیف قلم درخواست",
            "fields": [
                {"key": "item_name", "type": "text", "label": "شرح کالا/خدمات", "required": True, "colSpan": 16},
                {"key": "qty", "type": "integer", "label": "تعداد", "required": True, "min": 1, "colSpan": 4},
                {"key": "price", "type": "money", "label": "قیمت واحد (ریال)", "required": True, "min": 0, "colSpan": 4, "moneyUnit": "ریال"},
                {"key": "row_total", "type": "calculated", "label": "جمع ردیف", "formula": "qty * price", "colSpan": 24},
            ],
        })

        f_purchase = make_form("purchase_request", "فرم درخواست خرید", {
            "title": "درخواست خرید",
            "fields": [
                {"key": "sec_info", "type": "title", "label": "مشخصات درخواست‌دهنده"},
                {"key": "full_name", "type": "text", "label": "نام و نام خانوادگی", "required": True, "colSpan": 8},
                {"key": "national_id", "type": "national_id", "label": "کد ملی", "required": True, "colSpan": 8},
                {"key": "mobile", "type": "mobile", "label": "شماره موبایل", "required": True, "colSpan": 8},
                {"key": "request_date", "type": "jalali_date", "label": "تاریخ درخواست", "required": True, "colSpan": 6},
                {"key": "sec_req", "type": "title", "label": "مشخصات درخواست"},
                {"key": "unit_id", "type": "org_unit", "label": "واحد سازمانی", "required": True, "colSpan": 8},
                {"key": "request_type", "type": "select", "label": "نوع درخواست", "required": True,
                 "lookupId": req_type_l.id if req_type_l else None, "colSpan": 8},
                {"key": "priority", "type": "select", "label": "اولویت", "lookupId": priority_l.id if priority_l else None, "colSpan": 8},
                {"key": "items", "type": "subform", "label": "اقلام درخواست", "subformId": f_purchase_item.id,
                 "minRows": 1, "maxRows": 20, "colSpan": 24},
                {"key": "total_amount", "type": "calculated", "label": "مبلغ کل (ریال)", "formula": "SUM(items.row_total)", "colSpan": 12, "moneyUnit": "ریال"},
                {"key": "description", "type": "textarea", "label": "توضیحات", "colSpan": 24, "maxLength": 1000},
            ],
        })

        f_manager = make_form("manager_decision", "تصمیم مدیر", {
            "title": "بررسی و تصمیم مدیر",
            "fields": [
                {"key": "summary", "type": "summary", "label": "خلاصه درخواست"},
                {"key": "action", "type": "radio", "label": "تصمیم", "required": True, "colSpan": 24,
                 "options": [{"value": "approve", "label": "تأیید"}, {"value": "reject", "label": "رد"}, {"value": "revision", "label": "بازگشت برای اصلاح"}]},
                {"key": "comment", "type": "textarea", "label": "نظر مدیر", "colSpan": 24, "maxLength": 500},
            ],
        })

        f_finance = make_form("finance_view", "اطلاع‌رسانی مالی", {
            "title": "بررسی مالی",
            "fields": [
                {"key": "summary", "type": "summary", "label": "خلاصه درخواست"},
                {"key": "finance_note", "type": "textarea", "label": "یادداشت مالی", "colSpan": 24},
            ],
        })

        # ---------- فرایند نمونه ----------
        with open("data/bpmn/purchase_request.bpmn", encoding="utf-8") as fh:
            bpmn_xml = fh.read()
        p = db.scalar(select(ProcessDefinition).where(ProcessDefinition.key == "purchase_request"))
        if not p:
            p = ProcessDefinition(key="purchase_request", title="درخواست خرید",
                                  description="سناریوی نمونه سند §۳۵: ثبت، تأیید مدیر، سقف مبلغ، ثبت سفارش و اطلاع‌رسانی مالی",
                                  created_by_id=users["designer"].id)
            db.add(p)
            db.flush()
        if not p.versions:
            config = {"calendarId": cal.id if cal else None, "bindings": {
                "start": {"formDefinitionId": f_purchase.id},
                "Task_Submit": {"formDefinitionId": f_purchase.id, "assigneeType": "field", "assigneeValue": "_initiator_id"},
                "Task_ManagerApprove": {"formDefinitionId": f_manager.id,
                                        "assigneeType": "role", "assigneeValue": "manager",
                                        "decisionKey": "purchase_approval",
                                        "results": [
                                            {"value": "approve", "label": "تأیید"},
                                            {"value": "reject", "label": "رد"},
                                            {"value": "revision", "label": "بازگشت برای اصلاح"},
                                        ], "dueHours": 48},
                "Task_FinanceNotify": {"formDefinitionId": f_finance.id, "assigneeType": "role", "assigneeValue": "finance"},
                "Task_RegisterOrder": {"connector": "mock:register_order"},
            }}
            v = ProcessVersion(definition_id=p.id, version=1, bpmn_xml=bpmn_xml,
                               main_process_id="Process_PurchaseRequest", config_json=config,
                               created_by_id=users["designer"].id, change_note="نسخه نمونه سند",
                               status="published")
            v.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
            v.published_by_id = users["admin"].id
            db.add(v)
        db.commit()
        print("✅ داده اولیه با موفقیت ثبت شد.")
        print("   کاربران نمونه (گذرواژه همه:", DEFAULT_PASSWORD, "): admin, designer, formdesigner, publisher, basedata, manager, finance1, user1, monitor1, auditor1")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
