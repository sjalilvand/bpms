# -*- coding: utf-8 -*-
"""آزمون بار BPMS با Locust — فاز ۴ (سند §۳۲).

پروفایل‌ها:
- BpmsReadUser    : کاربر مطالعه‌ای — ورود، فهرست فرایندها، کارتابل، نمونه‌ها (بار مطالعه‌ای)
- BpmsProcessUser : کاربر عملیاتی — شروع درخواست خرید + تکمیل وظیفه ثبت (بار نوشتاری)
- BpmsManagerUser : مدیر — تخلیه صف گروهی (دریافت + تأیید)

اجرای smoke:
  locust -f scripts/load/locustfile.py --headless -u 10 -r 2 -t 30s \
      --host http://localhost:8000 --html report.html --csv load_result

متغیرهای محیطی:
  LOAD_PASSWORD (پیش‌فرض Bpms@1234)
"""
from __future__ import annotations

import os
import random
import time
import uuid

from locust import HttpUser, between, task

PASSWORD = os.environ.get("LOAD_PASSWORD", "Bpms@1234")
PROCESS_KEY = "purchase_request"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client: httpx_like, username: str) -> str | None:
    with client.post("/api/v1/auth/login",
                     json={"username": username, "password": PASSWORD},
                     name="POST /auth/login", catch_response=True) as resp:
        if resp.status_code == 200:
            return resp.json().get("access_token")
        resp.failure(f"login {username} → {resp.status_code}")
        return None


# سازگاری: httpx_like فقط نوع‌گذاری است
httpx_like = object


class BpmsReadUser(HttpUser):
    """کاربر مطالعه‌ای — بار مطالعه‌ای روی APIهای پرتکرار."""
    weight = 5
    wait_time = between(1, 3)

    def on_start(self):
        self.token = login(self.client, random.choice(["user1", "monitor1", "manager", "finance1"]))

    @task(4)
    def list_processes(self):
        self.client.get("/api/v1/processes", headers=_auth(self.token), name="GET /processes")

    @task(4)
    def inbox(self):
        self.client.get("/api/v1/tasks/inbox", headers=_auth(self.token), name="GET /tasks/inbox")

    @task(2)
    def my_instances(self):
        self.client.get("/api/v1/process-instances",
                        params={"scope": "mine", "page": 1, "page_size": 10},
                        headers=_auth(self.token), name="GET /process-instances?mine")

    @task(1)
    def notifications(self):
        self.client.get("/api/v1/notifications", headers=_auth(self.token), name="GET /notifications")

    @task(1)
    def health(self):
        self.client.get("/api/v1/health", name="GET /health")


class BpmsProcessUser(HttpUser):
    """کاربر عملیاتی — شروع فرایند خرید (سناریوی §۳۵) و تکمیل وظیفه ثبت."""
    weight = 2
    wait_time = between(2, 5)

    def on_start(self):
        self.token = login(self.client, "user1")
        self.process_id = None
        with self.client.get("/api/v1/processes", headers=_auth(self.token),
                             name="GET /processes (lookup)", catch_response=True) as resp:
            if resp.status_code == 200:
                for p in resp.json().get("items", []):
                    if p["key"] == PROCESS_KEY and p.get("published_version"):
                        self.process_id = p["id"]
                        break

    @task(3)
    def start_purchase(self):
        if not self.process_id:
            return
        business_key = f"LOAD-{uuid.uuid4().hex[:10]}"
        data = {
            "full_name": "کاربر بار",
            "national_id": "0684159414",
            "mobile": "09123456789",
            "request_date": time.strftime("%Y-%m-%d"),
            "unit_id": 1, "request_type": 1, "priority": 5,
            "items": [{"item_name": "اقلام بار", "qty": 2, "price": 3000000, "row_total": 6000000}],
            "description": "بار آزمایشی — شروع فرایند",
            "total_amount": 6000000,
        }
        with self.client.post("/api/v1/process-instances",
                              json={"definition_id": self.process_id, "data": data, "business_key": business_key},
                              headers=_auth(self.token), name="POST /process-instances",
                              catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"start → {resp.status_code}: {resp.text[:120]}")
                return
            self.instance_id = resp.json()["id"]
        # تکمیل وظیفه ثبت (تخصیص به شروع‌کننده)
        with self.client.get(f"/api/v1/process-instances/{self.instance_id}",
                             headers=_auth(self.token), name="GET /process-instances/{id}",
                             catch_response=True) as resp:
            if resp.status_code != 200:
                return
            tasks = [t for t in resp.json().get("tasks", []) if t["spec_id"] == "Task_Submit" and t["status"] == "ready"]
        if tasks:
            self.client.post(f"/api/v1/tasks/{tasks[0]['id']}/complete",
                             json={"data": {}, "result": None, "comment": ""},
                             headers=_auth(self.token), name="POST /tasks/{id}/complete")

    @task(2)
    def browse(self):
        self.client.get("/api/v1/process-instances", params={"page": 1, "page_size": 10},
                        headers=_auth(self.token), name="GET /process-instances")


class BpmsManagerUser(HttpUser):
    """مدیر — تخلیه صف گروهی: دریافت و تأیید وظایف مدیر (بار تصمیم‌گیری)."""
    weight = 1
    wait_time = between(2, 4)

    def on_start(self):
        self.token = login(self.client, "manager")

    @task(5)
    def claim_and_approve(self):
        with self.client.get("/api/v1/tasks/group", headers=_auth(self.token),
                             name="GET /tasks/group", catch_response=True) as resp:
            if resp.status_code != 200:
                return
            items = resp.json().get("items", [])
            targets = [t for t in items if t["spec_id"] == "Task_ManagerApprove"]
        if not targets:
            return
        t = targets[0]
        with self.client.post(f"/api/v1/tasks/{t['id']}/claim", headers=_auth(self.token),
                              name="POST /tasks/{id}/claim", catch_response=True) as resp:
            if resp.status_code != 200:
                return  # رقابت Claim — طبیعی است
        self.client.post(f"/api/v1/tasks/{t['id']}/complete",
                         json={"data": {"action": "approve"}, "result": "approve", "comment": "بار آزمایشی"},
                         headers=_auth(self.token), name="POST /tasks/{id}/complete (approve)")

    @task(1)
    def inbox(self):
        self.client.get("/api/v1/tasks/inbox", headers=_auth(self.token), name="GET /tasks/inbox")
