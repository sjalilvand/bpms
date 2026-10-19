# -*- coding: utf-8 -*-
"""اتصال پایگاه داده — SQLAlchemy 2.x

طبق سند: SQLite برای توسعه و PostgreSQL برای عملیات.
حداقل وابستگی به ویژگی‌های اختصاصی SQLite رعایت شده است.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


connect_args = {}
is_sqlite = settings.DATABASE_URL.startswith("sqlite")
if is_sqlite:
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

if is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")   # کلید خارجی فعال (قاعده سازگاری سند)
        cur.execute("PRAGMA journal_mode=WAL")  # بهبود هم‌زمانی خواندن
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
