# فاز ۵ — یکپارچه‌سازی: API بیرونی، ورود سازمانی (OIDC/LDAP) و کانکتور SOAP

این سند پیاده‌سازی گام پنجم سند را مستند می‌کند: **API بیرونی با کلید/امضای Webhook و idempotency**، **احراز هویت OIDC و LDAP**، **کانکتور SOAP** و **آزمون بار عملیاتی روی PostgreSQL**.

## ۱) API بیرونی با idempotency (`app/modules/external/`)

### فراخوانی سرویس‌های بیرونی (inbound) — `/api/v1/external/v1/...`

| مسیر | دامنه (scope) | توضیح |
|------|---------------|-------|
| `POST /external/v1/process-instances` | `instances.start` | شروع فرایند با `definition_key`/`definition_id` (+ `version_id` اختیاری) |
| `GET /external/v1/process-instances/{id}` | `instances.read` | وضعیت نمونه + وظایف باز |
| `POST /external/v1/tasks/{id}/complete` | `tasks.complete` | تکمیل وظیفه با داده/نتیجه/توضیح |

**احراز و امنیت:**
- هدر `X-API-Key` — شناسه کلید سرویس (مدل `ExternalClient`؛ رمز یک‌بار در ساخت/چرخش نمایش داده می‌شود)
- هدر `X-Timestamp` + `X-Signature` — امضای `HMAC-SHA256(secret, "{ts}.{body}")` با تلورانس ±۳۰۰ ثانیه (مقابله با بازپخش)؛ برای هر سرویس `require_signature` قابل تنظیم است
- دامنه‌های صریح (`scopes`) + سقف نرخ per-client (`rate_limit_per_min` → 429)
- کاربر نماینده (`actor_username`) — عملیات به‌نام او ثبت و ممیزی می‌شود

**Idempotency (سند §۳۳):**
- عملیات نوشتاری با هدر `Idempotency-Key` تکرارپذیرند
- fingerprint درخواست (`sha256(method+path+body)`) ذخیره می‌شود؛ تکرارِ همان درخواست → **بازپخش پاسخ اصلی** با هدر `X-Idempotent-Replay: true` (بدون ساخت نمونه/تکمیل دوم)
- همان کلید با محتوای متفاوت → **409 Conflict**
- سقف نگهداشت رکوردها با پاک‌سازی خودکار قدیمی‌ترین‌ها

### Webhook خروجی (outbound)

- مدیریت مقصدها: `GET/POST/DELETE /integrations/webhooks` — هر مقصد رویدادهای دلخواه (`*` یا فهرست) با رمز اختصاصی
- رویدادها: `instance.started` ، `task.created` ، `task.completed` ، `instance.completed` ، `instance.cancelled` — از قلب سرویس موتور با الگوی **انتشار پس از commit** (تراکنش ناموفق هرگز Webhook نمی‌فرستد)
- امضای هر ارسال: هدرهای `X-BPMS-Event` ، `X-BPMS-Timestamp` ، `X-BPMS-Signature: sha256=<HMAC(secret, "{ts}.{body}")>`
- تحویل در نخ پس‌زمینه با timeout و retry (۲ تلاش مجدد) — **خارج از تراکنش DB** تا قفل پایگاه رخ ندهد؛ گزارش کامل تلاش‌ها در `webhook_deliveries` + مشاهده در `/integrations/deliveries`

### مدیریت (پنل admin — مجوز `integration.manage`)
- `GET/POST/PUT /integrations/clients` + `POST /integrations/clients/{id}/rotate-secret`
- گزارش تحویل‌ها: `GET /integrations/deliveries?endpoint_id=`

## ۲) ورود سازمانی — OIDC و LDAP

### OIDC (Authorization Code Flow) — بدون وابستگی خارجی
- کشف پیکربندی از `/.well-known/openid-configuration` (کش ۱۰ دقیقه‌ای)
- `GET /auth/oidc/login` → هدایت به IdP با `state` امضاشده (JWT کوتاه‌عمر ۱۰ دقیقه‌ای شامل nonce — بدون نشست سمت سرور)
- `GET /auth/oidc/callback` → تبادل کد → userinfo → **تأمین خودکار کاربر** (`provision_user`) با نقش پیش‌فرض `BPMS_OIDC_DEFAULT_ROLE` → هدایت به صفحه ورود با `?oidc_token=` (AuthContext آن را برداشت و وارد می‌شود)
- خطاها به‌صورت `?oidc_error=state|exchange|identity|inactive` به صفحه ورود بازمی‌گردند با پیام فارسی
- پیکربندی (متغیرهای `BPMS_`): `OIDC_ENABLED` ، `OIDC_ISSUER` ، `OIDC_CLIENT_ID` ، `OIDC_CLIENT_SECRET` ، `OIDC_REDIRECT_URI` ، `OIDC_SCOPES` ، `OIDC_DEFAULT_ROLE`

### LDAP (bind-then-search با ldap3)
- اتصال با حساب خدماتی → یافتن DN کاربر (`LDAP_USER_FILTER` پیش‌فرض AD) → **bind مستقیم با گذرواژه کاربر** — هیچ گذرواژه‌ای در سامانه ذخیره نمی‌شود
- تأمین خودکار کاربر محلی هم‌نام با نقش `LDAP_DEFAULT_ROLE` (گذرواژه نمادین `!ldap-no-local-password` — ورود محلی برای این کاربران ممکن نیست)
- مسیر ورود: `POST /auth/login` ابتدا حساب محلی، سپس LDAP (در صورت `LDAP_ENABLED`)
- پیکربندی: `LDAP_ENABLED` ، `LDAP_URL` ، `LDAP_BIND_DN` ، `LDAP_BIND_PASSWORD` ، `LDAP_USER_BASE` ، `LDAP_USER_FILTER` ، `LDAP_DEFAULT_ROLE`
- صفحه ورود با `GET /auth/config` (عمومی) وضعیت را می‌گیرد و دکمه «ورود سازمانی» را فقط در صورت فعال بودن نشان می‌دهد

## ۳) کانکتور SOAP 1.1 (`engine/connectors.py`)

- فرمت: `soap:<URL>|<SOAPAction>` در کانکتور فعالیت سیستمی (مانند `soap:http://erp.local/api|CreateOrder`)
- ساخت پوش SOAP 1.1 از متغیرهای فرایند: پارامترهای ساده به‌صورت `<arg name="...">`؛ مقادیر پیچیده JSON؛ escape کامل XML؛ سقف ۵۰ پارامتر
- پاسخ: عنصر `Result` استخراج و به متغیرها ادغام می‌شود؛ `SOAP Fault` → خطا → حالت ERROR + Incident (AC-15)؛ timeout/retry هم‌سان با کانکتور http

## ۴) آزمون بار عملیاتی روی PostgreSQL

- محیط: PostgreSQL 16 + uvicorn تک‌پروسه + داده seed واقعی + پروفایل Locust «بار معمول» (۵۰ کاربر، ۲ دقیقه — ramp ۵/s)
- نتیجه: **۳٬۳۹۸ درخواست — نرخ خطای ۰٫۱۵٪** (تنها ۵ مورد 409 رقابت Claim که رفتار صحیح AC-12 است، نه خطا)

| مسیر | تعداد | p50 | p95 | p99 |
|------|-------|-----|-----|-----|
| POST /process-instances (شروع فرایند) | ۲۵۸ | ۱۹ms | ۵۴ms | ۸۵ms |
| POST /tasks/{id}/complete | ۲۵۸ | ۲۲ms | ۶۸ms | ۱۲۰ms |
| POST /tasks/{id}/complete (تأیید مدیر) | ۱۷۷ | ۲۴ms | ۴۹ms | ۹۶ms |
| GET /tasks/inbox | ۶۴۷ | ۷ms | ۲۰ms | ۳۵ms |
| GET /processes | ۶۱۴ | ۶ms | ۱۶ms | ۳۲ms |
| POST /auth/login (bcrypt عمداً کند) | ۵۰ | ۲۰۰ms | ۲۸۰ms | ۲۸۰ms |
| **Aggregated** | **۳٬۳۹۸** | **۱۱ms** | **۴۸ms** | **۱۹۰ms** |

- مقایسه با SQLite (فاز ۴): p95 جمع از ۶۹ms به ۴۸ms و p99 از ۹۱ms به ۱۹۰ms با ۵ برابر شدن کاربران — PostgreSQL فشار هم‌زمانی نوشتن را به‌روشنی بهتر جذب کرد (در SQLite آزمون ۵۰ کاربری به‌سرعت به قفل می‌رسید).
- فایل خام: `scripts/load/results-pg-stats.csv` — راهنمای تکرار: docs/load-testing.md

## ۵) آزمون‌ها

| مجموعه | شمار | وضعیت |
|--------|------|-------|
| pytest بک‌اند | ۱۵۹ (+۳۶ جدید: external ۱۹، SSO ۱۲، SOAP ۱۰ منهای هم‌پوشانی) | ✅ |
| Vitest فرانت‌اند | ۲۵ | ✅ |
| آزمون Webhook با سرور HTTP محلی + بررسی امضای HMAC | ۱ سناریوی کامل | ✅ |
| آزمون بار PostgreSQL (۵۰ کاربر × ۲ دقیقه) | ۳٬۳۹۸ درخواست / ۰٫۱۵٪ | ✅ |

## ۶) محدودیت‌های باقی‌مانده (شفاف‌سازی)

- محدودیت نرخ بیرونی per-process است (استقرار چندنمونه‌ای به Redis/NGINX limit نیاز دارد — نقطه توسعه مستند)
- OIDC از جریان Authorization Code استفاده می‌کند؛ PKCE و JWT-based IdP-specific ادعاها در گام بعد
- کانکتور SOAP پوش عمومی ساده است؛ WSDL-first و WS-Security فاز توسعه جداگانه
- delivery Webhook در نخ پس‌زمینه هر پروسه است؛ در استقرار چندنمونه‌ای صف توزیع‌شده (Celery) جایگزین بهتری است
