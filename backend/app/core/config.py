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

    class Config:
        env_file = ".env"
        env_prefix = "BPMS_"


settings = Settings()

Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
