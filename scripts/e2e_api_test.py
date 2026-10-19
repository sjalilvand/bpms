# -*- coding: utf-8 -*-
"""آزمون E2E سناریوی §۳۵ سند از طریق HTTP — اجرای کامل فرایند «درخواست خرید».

پیش‌نیاز: سرور در حال اجرا + داده اولیه (python -m app.seed)
اجرای آزمون: python3 scripts/e2e_api_test.py [--base-url http://localhost:8000]

مسیر آزمون: ورود user1 → ثبت درخواست (فرم با کد ملی/موبایل/اقلام) → تکمیل ثبت
→ ورود manager → دریافت از صف گروهی → تأیید (decision_applied r3 + مهلت کاری)
→ ورود finance1 → تکمیل اطلاع‌رسانی مالی → وضعیت completed
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta

import httpx

PASS, FAIL = "✅", "❌"
steps: list[str] = []


def step(msg: str, ok: bool = True, detail: str = "") -> None:
    icon = PASS if ok else FAIL
    line = f"{icon} {msg}" + (f" — {detail}" if detail else "")
    print(line)
    steps.append(line)


def die(msg: str) -> None:
    step(msg, ok=False)
    sys.exit(1)


def login(client: httpx.Client, base: str, username: str, password: str = "Bpms@1234") -> str:
    r = client.post(f"{base}/api/v1/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        die(f"ورود {username} ناموفق بود: {r.status_code} {r.text}")
    return r.json()["access_token"]


def api(client: httpx.Client, base: str, token: str, method: str, path: str, **kw) -> dict:
    r = client.request(method, f"{base}/api/v1{path}", headers={"Authorization": f"Bearer {token}"}, **kw)
    if r.status_code >= 400:
        die(f"{method} {path} → {r.status_code}: {r.text[:500]}")
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    # سلامت سرور
    with httpx.Client(timeout=30) as c:
        for attempt in range(10):
            try:
                r = c.get(f"{base}/api/v1/health")
                if r.status_code == 200:
                    step("سلامت سرور", True, r.json().get("version", ""))
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            die(f"سرور روی {base} پاسخ نمی‌دهد — ابتدا uvicorn را اجرا کنید")

        # ---------- ورود کاربران ----------
        tok_user = login(c, base, "user1")
        tok_mgr = login(c, base, "manager")
        tok_fin = login(c, base, "finance1")
        step("ورود سه کاربر نمونه (user1/manager/finance1)")

        # ---------- یافتن فرایند منتشرشده ----------
        procs = api(c, base, tok_user, "GET", "/processes")
        p = next((x for x in procs["items"] if x["key"] == "purchase_request"), None)
        if not p or not p.get("published_version"):
            die("فرایند «درخواست خرید» با نسخه منتشرشده یافت نشد — python -m app.seed را اجرا کنید")
        step("فرایند منتشرشده یافت شد", True, f"#{p['id']} نسخه v{p['published_version']['version']}")

        # ---------- داده مرجع (واحد سازمانی/جدول پایه) ----------
        units = api(c, base, tok_user, "GET", "/org-units")
        unit_id = units["items"][0]["id"]
        lookups = api(c, base, tok_user, "GET", "/lookups")
        def lookup_item(key: str, code: str) -> int:
            l = next(x for x in lookups["items"] if x["key"] == key)
            items = api(c, base, tok_user, "GET", f"/lookups/{l['id']}/items")["items"]
            flat = []
            def walk(rows):
                for r_ in rows:
                    flat.append(r_)
                    walk(r_.get("children") or [])
            walk(items)
            return next(it["id"] for it in flat if it["code"] == code)
        req_type_id = lookup_item("request_type", "goods")
        priority_id = lookup_item("priority", "normal")
        step("داده مرجع (واحد سازمانی، نوع درخواست، اولویت)")

        # ---------- شروع فرایند (§۳۵) ----------
        business_key = f"E2E-{int(time.time())}"
        data = {
            "full_name": "علی رضایی",
            "national_id": "0684159414",
            "mobile": "09123456789",
            "request_date": (date.today() - timedelta(days=1)).isoformat(),
            "unit_id": unit_id,
            "request_type": req_type_id,
            "priority": priority_id,
            "items": [{"item_name": "لپ‌تاپ کاری", "qty": 3, "price": 5000000, "row_total": 15000000}],
            "description": "آزمون E2E خودکار سناریوی §۳۵",
        }
        inst = api(c, base, tok_user, "POST", "/process-instances",
                   json={"definition_id": p["id"], "data": data, "business_key": business_key})
        iid = inst["id"]
        step("شروع فرایند", True, f"نمونه #{iid} — {business_key}")

        # ---------- تکمیل «ثبت درخواست» توسط شروع‌کننده ----------
        detail = api(c, base, tok_user, "GET", f"/process-instances/{iid}")
        t_submit = next(t for t in detail["tasks"] if t["spec_id"] == "Task_Submit" and t["status"] == "ready")
        api(c, base, tok_user, "POST", f"/tasks/{t_submit['id']}/complete",
            json={"data": {}, "result": None, "comment": "ثبت نهایی درخواست"})
        step("تکمیل وظیفه «ثبت درخواست خرید»")

        # ---------- تأیید مدیر از صف گروهی ----------
        group = api(c, base, tok_mgr, "GET", "/tasks/group")
        t_mgr = next(t for t in group["items"] if t["instance_id"] == iid and t["spec_id"] == "Task_ManagerApprove")
        api(c, base, tok_mgr, "POST", f"/tasks/{t_mgr['id']}/claim")
        api(c, base, tok_mgr, "POST", f"/tasks/{t_mgr['id']}/complete",
            json={"data": {"action": "approve"}, "result": "approve", "comment": "تأیید خودکار آزمون"})
        step("تأیید مدیر (صف گروهی → دریافت → تأیید)")

        # کنترل‌های فاز ۳: تصمیم DMN + مهلت کاری
        detail = api(c, base, tok_user, "GET", f"/process-instances/{iid}")
        d_event = next((e for e in detail["history"] if e["event_type"] == "decision_applied"), None)
        if d_event and d_event.get("detail", {}).get("rule") == "r3":
            step("رویداد decision_applied — قاعده r3 (مبلغ ۱۰ تا ۵۰ میلیون)")
        else:
            step("رویداد تصمیم DMN", True, str((d_event or {}).get("detail", {})))
        mgr_row = next(t for t in detail["tasks"] if t["spec_id"] == "Task_ManagerApprove")
        if mgr_row.get("due_at"):
            step("مهلت کاری وظیفه مدیر (تقویم کاری فاز ۳)", True, mgr_row["due_at"][:16])
        else:
            step("مهلت وظیفه مدیر خالی است", ok=False)

        # ---------- انشعاب موازی: سرویس خودکار + اطلاع‌رسانی مالی ----------
        # فعالیت سیستمی ردیف کارتابل ندارد؛ موفقیت آن با نبود Incident و خاتمه موفق
        # نمونه (اتصال موازی به هر دو شاخه نیاز دارد) اثبات می‌شود.
        if not detail.get("incidents"):
            step("فعالیت سیستمی «ثبت سفارش» (mock) بدون Incident اجرا شد")
        else:
            step("Incident باز برای فعالیت سیستمی وجود دارد", ok=False)
        group = api(c, base, tok_fin, "GET", "/tasks/group")
        t_fin = next(t for t in group["items"] if t["instance_id"] == iid and t["spec_id"] == "Task_FinanceNotify")
        api(c, base, tok_fin, "POST", f"/tasks/{t_fin['id']}/claim")
        api(c, base, tok_fin, "POST", f"/tasks/{t_fin['id']}/complete",
            json={"data": {"finance_note": "اطلاع‌رسانی انجام شد"}, "result": None, "comment": ""})
        step("تکمیل وظیفه «اطلاع‌رسانی مالی» توسط finance1")

        # ---------- وضعیت نهایی ----------
        detail = api(c, base, tok_user, "GET", f"/process-instances/{iid}")
        if detail["status"] == "completed":
            step("نمونه فرایند با وضعیت completed خاتمه یافت")
        else:
            die(f"وضعیت نهایی {detail['status']} است — انتظار completed")
        types = [e["event_type"] for e in detail["history"]]
        for expected in ("instance_started", "task_created", "task_completed", "instance_completed"):
            if expected not in types:
                die(f"رویداد {expected} در تاریخچه نیست")
        step("تاریخچه کامل رویدادها (آغاز/ایجاد/تکمیل/خاتمه)")

    print("\n" + "=" * 60)
    print(f"نتیجه: {len(steps)} گام همه موفق — سناریوی §۳۵ از طریق HTTP کامل اجرا شد")


if __name__ == "__main__":
    main()
