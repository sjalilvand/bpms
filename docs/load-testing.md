# آزمون بار BPMS — راهنما و نتایج نمونه (فاز ۴)

ابزار: **Locust** (پایتونی، توزیع‌پذیر) — سناریوها بازتاب‌دهنده کاربرد واقعی سامانه است، نه فقط درخواست‌زدن صفحه سلامت.

## سناریوها (scripts/load/locustfile.py)

| کلاس کاربر | وزن | رفتار |
|------------|-----|-------|
| `BpmsReadUser` | ۵ | ورود + فهرست فرایندها + کارتابل + نمونه‌های من + اعلان‌ها (بار مطالعه‌ای) |
| `BpmsProcessUser` | ۲ | شروع فرایند «درخواست خرید» با داده کامل §۳۵ + تکمیل وظیفه ثبت (بار نوشتاری) |
| `BpmsManagerUser` | ۱ | تخلیه صف گروهی: دریافت (Claim) + تأیید وظایف مدیر (بار تصمیم‌گیری با رقابت Claim) |

- شناسه درخواست (business_key) برای هر نمونه یکتا است تا داده تکراری ایجاد نشود.
- رقابت Claim بین مدیران عمدی است؛ پاسخ ۴۰۰ در رقابت شکست محسوب نمی‌شود (رفتار طبیعی AC-12).

## اجرا

```bash
# ۱) سرور با داده اولیه
cd backend && python -m app.seed && uvicorn app.main:app --port 8000

# ۲) نصب ابزار بار (یک‌بار)
pip install -r scripts/load/requirements.txt

# ۳) smoke — ۱۰ کاربر، ۳۰ ثانیه
locust -f scripts/load/locustfile.py --headless -u 10 -r 2 -t 30s \
    --host http://localhost:8000 --html report.html --csv load_result

# ۴) بار معمول — ۵۰ کاربر، ۵ دقیقه
locust -f scripts/load/locustfile.py --headless -u 50 -r 5 -t 5m --host http://localhost:8000

# ۵) فشار — افزایش تدریجی تا یافتن نقطه شکست
locust -f scripts/load/locustfile.py --headless -u 200 -r 10 -t 10m --host http://localhost:8000
```

نکته: در آزمون بار از SQLite استفاده می‌شود (پایلوت)؛ برای اعداد عملیاتی، PostgreSQL + uvicorn workers چندگانه را بر اساس docs/deployment.md پیکربندی کنید — SQLite محدودیت هم‌زمانی نوشتن دارد و اعداد فشار را محدود می‌کند.

## اهداف سطح خدمت (SLO) مرجع

| سنجه | هدف | وضعیت smoke |
|------|-----|-------------|
| نرخ خطا | < ۱٪ | ۰٪ ✅ |
| p95 مطالعه‌ای (processes/inbox/instances) | < ۳۰۰ms | ≤ ۲۳ms ✅ |
| p95 شروع فرایند (POST process-instances) | < ۸۰۰ms | ۲۶ms ✅ |
| p95 ورود (bcrypt عمداً کند است) | < ۵۰۰ms | ۹۴ms ✅ |

## نتیجه نمونه (smoke — ۱۰ کاربر، ۳۰ ثانیه، SQLite، تک‌پروسه uvicorn)

مجموع **۱۹۸ درخواست، ۰ خطا (۰٪)** — Aggregated: میانه ۹ms، p90 = ۲۱ms، p95 = ۶۹ms، بیشینه ۹۴ms.

| مسیر | تعداد | میانه | p95 |
|------|-------|-------|-----|
| POST /auth/login | ۱۰ | ۷۳ms | ۹۴ms |
| POST /process-instances (شروع فرایند) | ۲۰ | ۱۱ms | ۲۶ms |
| POST /tasks/{id}/complete (تأیید مدیر) | ۱۰ | ۱۳ms | ۳۶ms |
| GET /tasks/inbox | ۲۵ | ۶ms | ۱۳ms |
| GET /processes | ۳۱ | ۶ms | ۷ms |

فایل خام: `scripts/load/results-sample-stats.csv` (ستون‌های صدک در انتهای CSV).

## نتیجه عملیاتی (فاز ۵ — PostgreSQL ۱۶، ۵۰ کاربر، ۲ دقیقه)

```bash
# پس از تنظیم BPMS_DATABASE_URL به PostgreSQL
alembic upgrade head && python -m app.seed
BPMS_DATABASE_URL=... uvicorn app.main:app --port 8000
locust -f scripts/load/locustfile.py --headless -u 50 -r 5 -t 2m --host http://localhost:8000 \
    --csv load_pg --only-summary
```

مجموع **۳٬۳۹۸ درخواست (~۲۸ req/s)، نرخ خطای ۰٫۱۵٪** — تنها ۵ مورد 409 رقابت Claim
(رفتار صحیح AC-12، نه خطا). Aggregated: میانه ۱۱ms، **p95 = ۴۸ms**، p99 = ۱۹۰ms.

| مسیر | تعداد | p50 | p95 |
|------|-------|-----|-----|
| POST /process-instances (شروع فرایند) | ۲۵۸ | ۱۹ms | ۵۴ms |
| POST /tasks/{id}/complete | ۲۵۸ | ۲۲ms | ۶۸ms |
| POST /tasks/{id}/complete (تأیید مدیر) | ۱۷۷ | ۲۴ms | ۴۹ms |
| GET /tasks/inbox | ۶۴۷ | ۷ms | ۲۰ms |
| POST /auth/login | ۵۰ | ۲۰۰ms | ۲۸۰ms |

فایل خام: `scripts/load/results-pg-stats.csv`. همه SLOها با فاصله زیاد برقرارند؛
PostgreSQL هم‌زمانی نوشتن را به‌روشنی بهتر از SQLite جذب کرد.

## چک‌لیست پیش از آزمون عملیاتی

- [ ] PostgreSQL با connection pool مناسب و `synchronous_commit` بررسی‌شده
- [ ] uvicorn با چند worker (یا gunicorn) و پشت nginx (SSE در nginx فعال — docs/deployment.md)
- [ ] Worker پایدار Celery مستقل از وب اجرا می‌شود (BPMS_SCHEDULER_MODE=celery)
- [ ] پایش: لاگ کانکتورها، ممیزی، و نرخ Incident در حین بار
- [ ] داده حجمی واقع‌گرایانه (هزاران نمونه/وظیفه) نه دیتابیس خالی seed
