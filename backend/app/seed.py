# -*- coding: utf-8 -*-
"""داده اولیه سامانه: نقش‌ها، کاربران نمونه، جداول پایه، فرم‌ها و فرایند «درخواست خرید».

اجرا: python -m app.seed
سناریوی §۳۵ سند باید با این داده‌ها از ابتدا تا انتها قابل اجرا باشد.
"""
import json
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import SessionLocal, Base, engine
from app.core.security import hash_password
from app.modules.identity.models import Role, User
from app.modules.organization.models import OrganizationUnit
from app.modules.lookups.router import LookupDefinition, LookupItem
from app.modules.forms.models import FormDefinition, FormVersion
from app.modules.engine.models import ProcessDefinition, ProcessVersion
from app.modules.identity.router import ALL_PERMISSIONS

DEFAULT_PASSWORD = "Bpms@1234"


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # ---------- نقش‌ها ----------
        roles_spec = {
            "admin": ("مدیر سامانه", ["*"]),
            "process_designer": ("طراح فرایند", ["process.view", "process.manage", "form.view", "monitor.view"]),
            "form_designer": ("طراح فرم", ["form.view", "form.manage"]),
            "publisher": ("مسئول انتشار", ["process.view", "process.publish", "form.view", "form.publish"]),
            "base_data_admin": ("مدیر داده‌های پایه", ["lookup.manage", "form.view"]),
            "manager": ("مدیر واحد", ["task.claim", "task.complete", "process.start", "process.view", "monitor.view"]),
            "finance": ("کارشناس مالی", ["task.claim", "task.complete", "process.view"]),
            "operator": ("کاربر اجرایی", ["process.start", "task.claim", "task.complete"]),
            "monitor": ("ناظر فرایند", ["monitor.view", "process.view"]),
            "auditor": ("حسابرس", ["audit.view", "monitor.view"]),
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
            config = {"bindings": {
                "start": {"formDefinitionId": f_purchase.id},
                "Task_Submit": {"formDefinitionId": f_purchase.id, "assigneeType": "field", "assigneeValue": "_initiator_id"},
                "Task_ManagerApprove": {"formDefinitionId": f_manager.id,
                                        "assigneeType": "role", "assigneeValue": "manager",
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
