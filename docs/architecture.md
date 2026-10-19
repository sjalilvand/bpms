# معماری سامانه BPMS

## نمای منطقی (مطابق سند §۲۵)

```
React 18 + TypeScript + Vite (RTL فارسی)
│
├── طراح فرایند (bpmn-js)        ├── طراح فرم (dnd-kit)
├── نمایش‌دهنده فرم (Renderer)    ├── کارتابل
├── درخواست‌های من / پایش         ├── مدیریت (کاربر/نقش/داده پایه/سازمان)
└── مشاهده زنده نمودار و تاریخچه
          │  HTTPS / JSON  (axios + TanStack Query)
          ▼
FastAPI (پیشوند /api/v1، OpenAPI در /docs)
│
├── هویت و مجوز (JWT + bcrypt + RBAC صریح)
├── فرم و نسخه‌بندی (Schema-based)
├── تعریف و اجرای فرایند (ProcessDefinition/Version → Instance/Task/Event/Incident)
├── جداول پایه، اتصال‌ها (کانکتور)، اعلان، ممیزی
│
├── درگاه موتور BPMN (engine/adapter.py — SpiffWorkflow 3.2)
├── زمان‌بند سبک تایمر (svc.tick — در عملیات به Worker پایدار منتقل می‌شود)
└── SQLAlchemy 2.x → SQLite (WAL) → PostgreSQL
```

## اصل تفکیک سه جزء

طراح نمودار، فرم‌ساز و موتور اجرا سه جزء متفاوت‌اند:

- **طراح (bpmn-js)** فقط XML/BPMNDI تولید می‌کند و از اجرا بی‌خبر است.
- **تنظیمات فعالیت** (فرم متصل، مسئول، نتایج، کانکتور، مهلت) در `ProcessVersion.config_json` نگهداری می‌شود و از مدل BPMN جدا است؛ به این ترتیب انتشار مدل بدون پشتیبانی اجرایی ممکن نمی‌شود (اعتبارسنجی روی ترکیب مدل+اتصال‌ها انجام می‌گیرد).
- **موتور (SpiffWorkflow)** تنها از مسیر `engine/adapter.py` با بقیه سامانه صحبت می‌کند؛ وضعیت نمونه به‌صورت JSON سریالایز در `ProcessInstance.engine_state` ذخیره و پس از هر تعامل بازنویسی می‌شود (ذخیره پایدار + بازیابی AC-13).

## یافته‌های نمونه فنی فاز صفر (مبنای پیاده‌سازی آداپتور)

| موضوع | یافته |
|-------|-------|
| شناسه/نام عنصر | `task_spec.name` = شناسه فنی BPMN؛ نمایشی = `task_spec.bpmn_name` |
| وظایف انسانی | `task_spec.manual == True`؛ فهرست آماده: `get_tasks(state=READY)` |
| شرط دروازه | `conditionExpression` با معنای پایتونی روی متغیرهای وظیفه |
| تایمر | مقدار `timeDuration` باید رشته پایتونی کوتیشن‌دار باشد: `'PT1H'`؛ بیداری با `refresh_waiting_tasks` + یک گام اضافه |
| فعالیت سیستمی | پچ `ServiceTask._execute` → dispatch کانکتور؛ بازگشت `False` = حالت ERROR |
| رسیدگی به خطا | `get_tasks(state=ERROR)` + `run_task_from_id` برای تلاش مجدد کنترل‌شده |
| سریالایز | `BpmnWorkflowSerializer` با رجیستری سفارشی (ثبت `ServiceTask`) |
| تزریق داده اولیه | باید روی وظیفه آغاز (tasks[0]) انجام شود تا به شاخه‌های موازی برسد |

## طراحی داده (بر اساس §۲۶)

موجودیت‌ها: `User/Role`، `OrganizationUnit/Delegation`، `FormDefinition/FormVersion/FormSubmission`، `LookupDefinition/LookupItem`، `ProcessDefinition/ProcessVersion`، `ProcessInstance/EngineTask/InstanceEvent/Incident`، `Attachment`، `Notification`، `AuditLog`.

- **داده فرم**: مدل ترکیبی — فراداده/وضعیت رابطه‌ای، پاسخ فرم JSON نسخه‌بندی‌شده، زیرفرم با ردیف‌های مستقل درون همان JSON.
- **نسخه‌بندی**: `ProcessVersion` و `FormVersion` با وضعیت draft/published/archived؛ نمونه به `version_id` ثابت متصل است.
- **صف کارتابل**: جدول `engine_tasks` تصویر وظایف READY موتور است و پس از هر گام موتور همگام می‌شود (`_sync_tasks`).

## هم‌زمانی و یکپارچگی

- تکمیل وظیفه: کنترل وضعیت در تراکنش + بررسی مجوز → جلوگیری از تکمیل تکراری (AC-12).
- Claim گروهی: انتقال وضعیت ready→claimed با بررسی نقش؛ درخواست دوم 409 می‌گیرد.
- موتور و برنامه در یک تراکنش DB نیستند؛ ذخیره engine_state پس از هر گام idempotent است.
- در PostgreSQL می‌توان با `SELECT ... FOR UPDATE` قفل ردیف نمونه را افزودن کرد (نقطه توسعه مستند شده).

## امنیت

- گذرواژه bcrypt، توکن JWT با انقضا، خروج سمت کلاینت.
- مجوزها صریح و لیست‌پذیر (`/api/v1/permissions`)؛ عضویت سازمانی خودش مجوز نمی‌دهد.
- فایل‌ها خارج از مسیر اجرایی با نام تصادفی + پسوندهای مسدود + محدودیت حجم؛ دانلود با احراز هویت.
- XML ورودی فقط از مسیر پارسر موتور (lxml) و با سقف ساختار؛ XXE پیش‌فرض غیرفعال.
- ارزیاب فرمول اختصاصی بدون eval/exec؛ اسکریپت موتور در محیط محدود (بدون import/open).
- پوشاندن مقادیر حساس (password/token/secret) در لاگ کانکتورها.
