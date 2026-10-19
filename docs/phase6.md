# فاز ۶ — PKCE، صف توزیع‌شده Webhook و گزارش‌ساز/KPI

این سند پیاده‌سازی سه قابلیت درخواستی فاز ۶ را مستند می‌کند. همه تغییرات با
تست اختصاصی پوشش داده شده‌اند (۲۹ آزمون جدید؛ مجموع ۱۸۸ آزمون backend).

## ۱) PKCE برای OIDC (RFC 7636)

جریان Authorization Code حالا همیشه با **PKCE روش S256** کار می‌کند:

- `app/modules/identity/oidc.py`:
  - `generate_pkce_pair()` — تولید `code_verifier` (base64url، ۶۴ نویسه) و
    `code_challenge = BASE64URL(SHA256(verifier))` بدون کاراکتر `=`.
  - `make_state(nonce, code_verifier)` — verifier داخل همان **state امضاشده JWT**
    حمل می‌شود؛ بدون session سمت سرور (سازگار با معماری فاز ۵).
  - `parse_state_data(state)` — خواندن کامل nonce + verifier؛
    `parse_state()` برای سازگاری رو به عقب همچنان فقط nonce می‌دهد.
  - `build_authorize_url()` — افزودن `code_challenge` و
    `code_challenge_method=S256` به درخواست مجاز.
  - `exchange_code(code, code_verifier)` — ارسال `code_verifier` در تبادل توکن.
- **client_secret اکنون اختیاری است** (کلاینت عمومی): اگر خالی باشد به
  token endpoint فرستاده نمی‌شود؛ PKCE جایگزین احراز کلاینت می‌شود.
- تنظیم جدید: `BPMS_OIDC_PKCE_ENABLED` (پیش‌فرض `true`) — برای IdPهای
  ناسازگار قابل خاموش‌کردن است.
- نقطه تماس callback: `app/modules/identity/router.py::oidc_callback` —
  verifier از state استخراج و به تبادل کد پاس می‌شود.
- آزمون‌ها: `tests/test_sso.py::TestPKCE` (رعایت RFC، یکتایی جفت‌ها،
  حمل verifier در state، URL مجاز، secret اختیاری، مسیر کامل callback).

## ۲) صف توزیع‌شده Webhook با Celery

ارسال Webhook از «نخ پس‌زمینه در هر فرایند» به **صف توزیع‌شده Celery/Redis**
ارتقا یافت (تکمیل توصیه مستند در docs/phase5.md §۶):

- `app/modules/external/webhooks.py`:
  - `_create_deliveries(ev)` — ثبت ردیف‌های `WebhookDelivery` (pending) در
    نشست کوتاه‌عمر؛ مشترک میان هر دو مسیر.
  - `_dispatch_via_celery(ev)` — در `BPMS_SCHEDULER_MODE=celery` برای هر ردیف
    تسک `bpms.webhooks.deliver` روی صف `bpms` منتشر می‌شود؛ در نبود Broker
    یا خطای انتشار، خودکار به مسیر نخ پس‌زمینه برمی‌گردد (fallback).
  - `_deliver_single(delivery_id)` — **یک تلاش HTTP** برای ردیف ذخیره‌شده با
    امضای HMAC-SHA256؛ موفق → `success`، شکست با سهم باقی‌مانده →
    `TransientDeliveryFailure` (برای retry)، اتمام سهم → `failed`.
  - `sweep_stale_deliveries()` — بازیابی ردیف‌های pending یتیم (سقوط Worker):
    دوباره‌صف‌کردن ردیف‌های قدیمی‌تر از ۱۰ دقیقه با سهم باقی‌مانده و
    رد کردن (failed) سهم اتمام‌یافته.
- `app/worker/celery_app.py` — تسک‌های جدید:
  - `bpms.webhooks.deliver` — `bind=True`، `acks_late=True`،
    retry با **backoff نمایی ۱۰s تا ۳۰۰s**، سقف ۵ تلاش کل.
  - `bpms.webhooks.sweep` — در beat هر ۵ دقیقه (`webhook-sweep-every-5m`).
- حفظ تضمین‌های فاز ۵: انتشار فقط پس از commit، دورریز شدن با rollback،
  امضای خروجی و گزارش تحویل بدون تغییر.
- در حالت `inprocess` (توسعه/پایلوت/آزمون) رفتار نخ پس‌زمینه پیشین حفظ شده است.
- آزمون‌ها: `tests/test_webhook_queue.py` — موفقیت با امضا، شکست موقت
  (pending + raise)، بازیابی پس از شکست، اتمام سهم، skip ردیف موفق،
  sweeper، مسیریابی به Celery، fallback و ثبت تسک‌ها/beat.

### اجرا در عملیات

```bash
export BPMS_SCHEDULER_MODE=celery
celery -A app.worker.celery_app worker --loglevel=info -Q bpms -B
# یا جداگانه: celery -A app.worker.celery_app beat
```

## ۳) گزارش‌ساز و KPI

ماژول جدید `app/modules/reports/` (مدل + سرویس + API) با صفحه فرانت
`/reports` (منوی «گزارش‌ساز و KPI» با مجوز `report.view`):

- مجموعه‌داده‌ها (`app/modules/reports/service.py`):
  - **شاخص‌های کلی (overview)** — تعداد و وضعیت نمونه‌ها، نرخ تکمیل،
    میانگین/مین/ماکس/صدک ۵۰ و ۹۵ زمان چرخه (شروع تا پایان نمونه)،
    شمار وظایف به تفکیک وضعیت، میانگین انتظار و رسیدگی، شاخص‌های SLA
    (هشدار، فرازدگی، نرخ نقض)، میانگین نمونه در روز.
  - **گلوگاه‌ها (bottlenecks)** — گروه‌بندی بر گام فرایند (`spec_id`):
    ایجاد/تکمیل/در انتظار، میانگین انتظار و رسیدگی، بیشترین و صدک ۹۵،
    سرریز فعال و فرازدگی SLA؛ مرتب‌شده بر بدترین رسیدگی.
  - **بار کاری (workload)** — به تفکیک کاربر و صف گروهی (نقش):
    تکمیل‌شده، بار فعال جاری، سرریز فعال، فرازدگی، میانگین رسیدگی.
  - **حجم روزانه (volume)** — شروع و تکمیل هر روز در بازه.
- فیلترهای مشترک: `days` (۷/۳۰/۹۰/۳۶۵) یا `date_from/date_to`،
  `definition_id` و برای overview `status`.
- **گزارش‌های ذخیره‌شده** — جدول `saved_reports` (مایگریشن
  `c3d8e5a71f20`) با ذخیره dataset + فیلترها و اجرای دوباره؛
  مجوز `report.manage` برای ایجاد/حذف و `report.view` برای اجرا.
- APIها (پیشوند `/api/v1`):
  `GET /reports/kpi/overview|bottlenecks|workload|volume`،
  `GET /reports/options`،
  `GET|POST /reports/saved`، `DELETE /reports/saved/{id}`،
  `GET /reports/saved/{id}/run` — همگی لاگ ممیزی دارند.
- فرانت `frontend/src/pages/ReportsPage.tsx` — کارت‌های KPI، نمودار
  میله‌ای سبک حجم روزانه (بدون وابستگی جدید)، جدول گلوگاه‌ها و بار کاری،
  مدیریت گزارش‌های ذخیره‌شده؛ تاریخ‌ها با تقویم جلالی.
- مجوزهای جدید در `ALL_PERMISSIONS`: `report.view`، `report.manage`؛
  در seed به نقش‌های manager/monitor/auditor اضافه شد.
- آزمون‌ها: `tests/test_reports.py` — دقت محاسبات (چرخه، انتظار، رسیدگی،
  SLA)، فیلتر وضعیت، گلوگاه، بار کاری، حجم، مجوزها و چرخه عمر گزارش ذخیره‌شده.

## آزمون و اعتبارسنجی

```bash
cd backend && python -m pytest -q          # ۱۸۸ passed
cd frontend && npm run test -- --run       # ۲۵ passed
cd frontend && npx tsc --noEmit            # بدون خطا
BPMS_DATABASE_URL=sqlite:////tmp/x.db alembic upgrade head   # زنجیره مایگریشن سالم
```
