# راهنمای استقرار و ارتقا

## محیط‌ها

- **توسعه**: SQLite + uvicorn --reload + vite dev (پروکسی /api)
- **آزمون/پیش‌تولید/تولید**: همان کد با متغیرهای محیطی؛ دیتابیس PostgreSQL

## متغیرهای محیطی (پیشوند `BPMS_`)

| متغیر | پیش‌فرض | توضیح |
|-------|---------|-------|
| `BPMS_DATABASE_URL` | `sqlite:///.../backend/bpms.db` | برای PostgreSQL: `postgresql+psycopg://user:pass@host/bpms` |
| `BPMS_JWT_SECRET` | مقدار توسعه | **در عملیات حتماً تغییر دهید** |
| `BPMS_UPLOAD_DIR` | `backend/uploads` | فضای پایدار + پشتیبان‌گیری |
| `BPMS_MAX_UPLOAD_MB` | 20 | سقف حجم پیوست |
| `BPMS_TIMEZONE` | Asia/Tehran | نمایش رویدادها |

نمونه فایل: `.env.example` در ریشه `backend/`.

## گام‌های استقرار (SQLite — پایلوت)

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
python -m app.seed            # فقط بار اول
uvicorn app.main:app --port 8000
```

فایل دیتابیس روی فضای پایدار نگهداری شود. پشتیبان‌گیری با روش سازگار با وضعیت دیتابیس
(مثلاً `sqlite3 bpms.db ".backup 'backup.db'"`) و نه کپی فایل در حین نوشتن.

## گام‌های استقرار (PostgreSQL — عملیات)

1. ایجاد پایگاه و کاربر اختصاصی + نصب درایور: `pip install psycopg[binary]`
2. `BPMS_DATABASE_URL` را تنظیم و `alembic upgrade head` اجرا کنید (ساختار ساخته می‌شود).
3. **انتقال داده** (برنامه سند §۲۷.۳):
   - پشتیبان‌گیری و آزمون بازیابی از SQLite
   - توقف/کنترل نوشتن
   - انتقال داده با حفظ شناسه‌ها (جدول‌به‌جدول با همان ترتیب وابستگی‌ها؛ ابزار `pgloader` یا اسکریپت)
   - کنترل تعداد/ارتباط رکوردها و تطبیق `engine_state` (JSON مستقل از دیتابیس است)
   - آزمون وظایف جاری و تایمرها (endpoint `/api/v1/process-instances/{id}/tick`)
4. پایش پس از انتقال و تعیین تکلیف داده‌های ثبت‌شده در بازه انتقال (برنامه بازگشت سند).

> توجه سند: Alembic فقط ساختار را مدیریت می‌کند؛ انتقال داده و تفاوت‌های رفتاری نیاز به اجرای برنامه بالا دارد.

## Build فرانت‌اند

```bash
cd frontend && npm ci && npm run build
```

خروجی `frontend/dist` به‌صورت خودکار توسط FastAPI سرو می‌شود (مسیرهای غیر API به SPA برمی‌گردند).
Build باید ثابت و نسخه‌بندی‌شده در CI تولید شود.

## پایش و سلامت

- `GET /api/v1/health` — سلامت API
- `POST /api/v1/engine/tick` — بررسی تایمرهای نمونه‌های در جریان (زمان‌بندی دوره‌ای با cron / celery-beat در عملیات)
- لاگ uvicorn + لاگ ممیزی درون سامانه (`/audit`)

## ارتقا

1. پشتیبان‌گیری از دیتابیس و `uploads/`
2. استقرار نسخه جدید کد
3. `alembic upgrade head`
4. اجرای آزمون‌ها: `pytest` (بک‌اند)، `npm run test` (رابط)
5. بررسی نمونه‌های در جریان پس از ارتقا (بازیابی engine_state)

## فاز ۳ — Worker پایدار، SSE و متغیرهای محیطی جدید

### متغیرهای محیطی فاز ۳

| متغیر | پیش‌فرض | توضیح |
|-------|---------|-------|
| `BPMS_SCHEDULER_MODE` | `inprocess` | `inprocess` برای توسعه/پایلوت، `celery` برای عملیات |
| `BPMS_TICK_SECONDS` | `30` | فاصله تیک موتور (حالت inprocess) |
| `BPMS_SLA_SECONDS` | `300` | فاصله بررسی SLA (حالت inprocess) |
| `BPMS_SLA_WARN_PCT` | `80` | آستانه هشدار SLA (درصد کل زمان مجاز) |
| `BPMS_REDIS_URL` | خالی | فعال‌سازی پل SSE چندفرایندی (اختیاری) |
| `BPMS_CELERY_BROKER_URL` | `redis://localhost:6379/1` | بروکر Celery (حالت celery) |

### استقرار عملیاتی با Celery

```bash
export BPMS_SCHEDULER_MODE=celery
export BPMS_CELERY_BROKER_URL=redis://<redis-host>:6379/1

# worker + beat (نمونه کوچک)
celery -A app.worker.celery_app worker --loglevel=info -Q bpms -B

# مقیاس بزرگ‌تر: worker ها جدا و beat فقط روی یک نمونه
celery -A app.worker.celery_app worker --loglevel=info -Q bpms -c 2
celery -A app.worker.celery_app beat --loglevel=info
```

- در حالت `celery`، uvicorn زمان‌بند درون‌فرایندی را اجرا نمی‌کند (جلوگیری از تیک دوباره).
- وظایف: `bpms.engine.tick` (هر ۳۰ ثانیه) و `bpms.tasks.sla_check` (هر ۵ دقیقه).

### SSE پشت reverse-proxy

جریان `/api/v1/events/stream` با `text/event-stream` سرو می‌شود؛ برای nginx:

```nginx
location /api/v1/events/stream {
    proxy_pass http://bpms_backend;
    proxy_http_version 1.1;
    proxy_set_header Connection '';
    proxy_buffering off;          # حیاتی: بافر نباید پاسخ را نگه دارد
    proxy_read_timeout 3600s;
}
```

اگر چند نمونه uvicorn پشت load-balancer دارید، `BPMS_REDIS_URL` را تنظیم کنید تا
رویدادها از طریق Redis بین همه نمونه‌ها هم‌رسانی شود؛ در غیر این صورت اتصال‌های
هر نمونه فقط رویدادهای محلی همان نمونه را می‌گیرند.
