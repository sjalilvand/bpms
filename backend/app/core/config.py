# -*- coding: utf-8 -*-
"""تنظیمات سامانه BPMS — مقادیر از متغیرهای محیطی خوانده می‌شود."""
from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/


class Settings(BaseSettings):
    APP_NAME: str = "سامانه مدیریت فرایندهای کسب‌وکار (BPMS)"
    APP_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # دیتابیس: SQLite برای توسعه؛ PostgreSQL برای عملیات
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'bpms.db'}"

    # امنیت
    JWT_SECRET: str = "bpms-change-me-in-production-1f4a9c"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24

    # فایل‌ها
    UPLOAD_DIR: str = str(BASE_DIR / "uploads")
    MAX_UPLOAD_MB: int = 20

    # منطقه زمانی نمایش
    TIMEZONE: str = "Asia/Tehran"

    # CORS (توسعه فرانت‌اند)
    CORS_ORIGINS: str = "*"

    # ---------- فاز ۳ ----------
    # زمان‌بند: inprocess (پیش‌فرض توسعه/پایلوت) یا celery (عملیات — Worker پایدار)
    SCHEDULER_MODE: str = "inprocess"
    # فاصله تیک موتور و بررسی SLA برای زمان‌بند درون‌فرایندی
    TICK_SECONDS: int = 30
    SLA_SECONDS: int = 300
    # آستانه هشدار SLA (درصد از کل زمان مجاز)
    SLA_WARN_PCT: int = 80
    # Redis اختیاری برای پل SSE در استقرار چندفرایندی (بدون آن هم SSE کار می‌کند)
    REDIS_URL: str = ""
    # Celery (فقط در SCHEDULER_MODE=celery استفاده می‌شود)
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = ""

    # ---------- فاز ۵ — یکپارچه‌سازی ----------
    # ورود سازمانی OIDC (Authorization Code) — خالی = غیرفعال
    OIDC_ENABLED: bool = False
    OIDC_ISSUER: str = ""                 # مانند https://sso.example.com/realms/bpms
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_REDIRECT_URI: str = ""           # مانند http://bpms.example.com/api/v1/auth/oidc/callback
    OIDC_SCOPES: str = "openid profile email"
    OIDC_DEFAULT_ROLE: str = "operator"   # نقش خودکار کاربران تازه‌تأمین‌شده
    # فاز ۶ — PKCE (RFC 7636): به‌طور پیش‌فرض فعال؛ برای IdP ناسازگار خاموش شود.
    # با فعال بودن PKCE، client_secret اختیاری است (کلاینت عمومی).
    OIDC_PKCE_ENABLED: bool = True
    # احراز هویت LDAP — خالی = غیرفعال
    LDAP_ENABLED: bool = False
    LDAP_URL: str = ""                    # ldap://dc.example.local:389 یا ldaps://...
    LDAP_BIND_DN: str = ""                # حساب خدماتی جست‌وجو
    LDAP_BIND_PASSWORD: str = ""
    LDAP_USER_BASE: str = ""              # مانند OU=Users,DC=example,DC=local
    LDAP_USER_FILTER: str = "(&(objectClass=user)(sAMAccountName={username}))"
    LDAP_DEFAULT_ROLE: str = "operator"

    class Config:
        env_file = ".env"
        env_prefix = "BPMS_"


settings = Settings()

Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
