# -*- coding: utf-8 -*-
"""فاز ۵ — ورود سازمانی OIDC (Authorization Code Flow) بدون وابستگی خارجی.

- کشف پیکربندی از /.well-known/openid-configuration (با کش کوتاه‌عمر)
- ساخت URL مجاز با state امضاشده (JWT کوتاه‌عمر شامل nonce)
- تبادل کد با توکن‌endpoint و دریافت userinfo
- تأمین خودکار کاربر (provisioning) با نقش پیش‌فرض قابل پیکربندی
"""
from __future__ import annotations

import secrets
import time
import logging

import httpx

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token

logger = logging.getLogger("bpms.oidc")

_DISCOVERY_CACHE: dict = {"ts": 0.0, "data": None}
DISCOVERY_TTL = 600  # ثانیه


class OIDCError(Exception):
    pass


def oidc_configured() -> bool:
    return bool(settings.OIDC_ENABLED and settings.OIDC_ISSUER and settings.OIDC_CLIENT_ID)


def discover() -> dict:
    """نقشه پیکربندی IdP با کش ۱۰ دقیقه‌ای."""
    now = time.time()
    if _DISCOVERY_CACHE["data"] and now - _DISCOVERY_CACHE["ts"] < DISCOVERY_TTL:
        return _DISCOVERY_CACHE["data"]
    url = settings.OIDC_ISSUER.rstrip("/") + "/.well-known/openid-configuration"
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        raise OIDCError(f"دریافت پیکربندی OIDC ممکن نشد: {e}")
    _DISCOVERY_CACHE.update(ts=now, data=data)
    return data


def make_state(nonce: str) -> str:
    """state امضاشده سمت سرور — بدون session سمت سرور."""
    return create_access_token("oidc-state", {"nonce": nonce}, )


def parse_state(state: str) -> str | None:
    payload = decode_access_token(state or "")
    if not payload or payload.get("sub") != "oidc-state":
        return None
    # انقضای کوتاه: create_access_token از تنظیمات عمومی استفاده می‌کند؛
    # برای state مهلت اختصاصی بررسی می‌شود (iat)
    iat = payload.get("iat") or 0
    if time.time() - float(iat) > 600:
        return None
    return payload.get("nonce")


def build_authorize_url() -> str:
    conf = discover()
    endpoint = conf.get("authorization_endpoint")
    if not endpoint:
        raise OIDCError("authorization_endpoint در پیکربندی IdP یافت نشد")
    nonce = secrets.token_urlsafe(16)
    state = make_state(nonce)
    params = {
        "response_type": "code",
        "client_id": settings.OIDC_CLIENT_ID,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "scope": settings.OIDC_SCOPES,
        "state": state,
        "nonce": nonce,
    }
    query = "&".join(f"{k}={_urlquote(v)}" for k, v in params.items())
    return f"{endpoint}?{query}"


def _urlquote(v: str) -> str:
    from urllib.parse import quote
    return quote(v, safe="")


def exchange_code(code: str) -> dict:
    """تبادل کد → توکن‌ها → userinfo."""
    conf = discover()
    token_endpoint = conf.get("token_endpoint")
    userinfo_endpoint = conf.get("userinfo_endpoint")
    if not token_endpoint or not userinfo_endpoint:
        raise OIDCError("token/userinfo endpoint در پیکربندی IdP یافت نشد")
    try:
        resp = httpx.post(token_endpoint, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.OIDC_REDIRECT_URI,
            "client_id": settings.OIDC_CLIENT_ID,
            "client_secret": settings.OIDC_CLIENT_SECRET,
        }, timeout=15.0)
        resp.raise_for_status()
        tokens = resp.json()
        ui = httpx.get(userinfo_endpoint, headers={
            "Authorization": f"Bearer {tokens.get('access_token', '')}"}, timeout=15.0)
        ui.raise_for_status()
        return ui.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("OIDC exchange failed: %s", e)
        raise OIDCError("تبادل کد با سرویس هویت ناموفق بود")


def extract_username(userinfo: dict) -> str | None:
    for key in ("preferred_username", "upn", "email", "sub"):
        v = userinfo.get(key)
        if v:
            return str(v).split("@")[0] if key == "email" and v else str(v)
    return None
