# -*- coding: utf-8 -*-
"""فاز ۵ — احراز هویت LDAP (bind-then-search) با ldap3 — بدون ذخیره گذرواژه در سامانه.

جریان: اتصال با حساب خدماتی → یافتن DN کاربر بر اساس فیلتر → bind با گذرواژه کاربر.
در صورت موفقیت، کاربر محلی هم‌نام یافت/تأمین می‌شود (بدون گذرواژه محلی).
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.identity.models import Role, User

logger = logging.getLogger("bpms.ldap")


class LDAPError(Exception):
    pass


def ldap_configured() -> bool:
    return bool(settings.LDAP_ENABLED and settings.LDAP_URL and settings.LDAP_USER_BASE)


def provision_user(db: Session, username: str, full_name: str, email: str | None) -> User:
    """یافتن یا تأمین خودکار کاربر LDAP با نقش پیش‌فرض (بدون گذرواژه محلی)."""
    u = db.scalar(select(User).where(User.username == username))
    if u:
        return u
    role = db.scalar(select(Role).where(Role.code == (settings.LDAP_DEFAULT_ROLE or "operator")))
    u = User(username=username, password_hash="!ldap-no-local-password",
             full_name=full_name or username, email=email, is_active=True, is_superadmin=False)
    if role:
        u.roles.append(role)
    db.add(u)
    db.flush()
    return u


def authenticate_ldap(db: Session, username: str, password: str) -> User | None:
    """ورود LDAP؛ ناموفق → None (پیام‌ها در لاگ)."""
    if not username or not password:
        return None
    try:
        from ldap3 import Server, Connection, ALL  # وابستگی اختیاری فاز ۵
    except ImportError as e:  # pragma: no cover
        raise LDAPError("بسته ldap3 نصب نشده است (pip install ldap3)") from e

    server = Server(settings.LDAP_URL, get_info=ALL, connect_timeout=8)
    try:
        # ۱) اتصال با حساب خدماتی برای یافتن DN کاربر
        if settings.LDAP_BIND_DN:
            admin = Connection(server, user=settings.LDAP_BIND_DN,
                               password=settings.LDAP_BIND_PASSWORD, auto_bind=True)
            admin.unbind()
        search_conn = Connection(server, user=settings.LDAP_BIND_DN or None,
                                 password=settings.LDAP_BIND_PASSWORD or None,
                                 auto_bind=True)
        filt = settings.LDAP_USER_FILTER.format(username=username)
        search_conn.search(settings.LDAP_USER_BASE, filt,
                           attributes=["mail", "displayName", "cn", "sAMAccountName", "uid"])
        if not search_conn.entries:
            search_conn.unbind()
            return None
        entry = search_conn.entries[0]
        user_dn = entry.entry_dn
        display = str(entry.displayName) if "displayName" in entry else (str(entry.cn) if "cn" in entry else username)
        mail = str(entry.mail) if "mail" in entry and entry.mail else None
        search_conn.unbind()

        # ۲) bind مستقیم کاربر با گذرواژه
        user_conn = Connection(server, user=user_dn, password=password, auto_bind=True)
        user_conn.unbind()
    except LDAPError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning("LDAP authentication failed for %s: %s", username, e)
        return None

    return provision_user(db, username, display, mail)
