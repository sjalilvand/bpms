# -*- coding: utf-8 -*-
"""فاز ۵/۶ — ورود سازمانی OIDC (Authorization Code Flow + PKCE) بدون وابستگی خارجی.

- کشف پیکربندی از /.well-known/openid-configuration (با کش کوتاه‌عمر)
- ساخت URL مجاز با state امضاشده (JWT کوتاه‌عمر شامل nonce)
- فاز ۶: PKCE (RFC 7636) با S256 — code_verifier داخل state امضاشده حمل می‌شود
  و در تبادل کد به token endpoint بازگردانده می‌شود؛ برای کلاینت‌های عمومی
  client_secret اختیاری است.
- تبادل کد با توکن‌endpoint و دریافت userinfo
- تأمین خودکار کاربر (provisioning) با نقش پیش‌فرض قابل پیکربندی
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
import logging

import httpx

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token

logger = logging.getLogger("bpms.oidc")

_DISCOVERY_CACHE: dict = {"ts": 0.0, "data": None}
DISCOVERY_TTL = 600  # ثانیه
STATE_TTL = 600      # عمر مجاز state در ثانیه


class OIDCError(Exception):
    pass


def oidc_configured() -> bool:
    """فعال‌سازی OIDC — secret دیگر الزامی نیست (PKCE جایگزین می‌شود)."""
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


# ---------- PKCE (RFC 7636) — فاز ۶ ----------

def generate_pkce_pair() -> tuple[str, str]:
    """جفت (code_verifier, code_challenge) با روش S256.

    - verifier: رشته base64url با طول ۶۴ نویسه (محدوده مجاز RFC: ۴۳ تا ۱۲۸)
    - challenge: BASE64URL(SHA256(verifier)) بدون کاراکتر «=»
    """
    verifier = secrets.token_urlsafe(48)[:64]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def pkce_enabled() -> bool:
    """PKCE به‌طور پیش‌فرض فعال است؛ برای IdPهای ناسازگار قابل خاموش‌کردن است."""
    return bool(getattr(settings, "OIDC_PKCE_ENABLED", True))


def make_state(nonce: str, code_verifier: str | None = None) -> str:
    """state امضاشده سمت سرور — بدون session سمت سرور.

    code_verifier داخل همان JWT امضاشده حمل می‌شود (فاز ۶ — PKCE).
    """
    extra: dict = {"nonce": nonce}
    if code_verifier:
        extra["verifier"] = code_verifier
    return create_access_token("oidc-state", extra)


def parse_state_data(state: str) -> dict | None:
    """خواندن محتوای کامل state امضاشده (nonce + verifier اختیاری)."""
    payload = decode_access_token(state or "")
    if not payload or payload.get("sub") != "oidc-state":
        return None
    iat = payload.get("iat") or 0
    if time.time() - float(iat) > STATE_TTL:
        return None
    return payload


def parse_state(state: str) -> str | None:
    """فقط nonce (سازگار با نسخه پیشین) — برای کدهای موجود."""
    data = parse_state_data(state)
    return data.get("nonce") if data else None


def build_authorize_url() -> str:
    conf = discover()
    endpoint = conf.get("authorization_endpoint")
    if not endpoint:
        raise OIDCError("authorization_endpoint در پیکربندی IdP یافت نشد")
    nonce = secrets.token_urlsafe(16)
    params = {
        "response_type": "code",
        "client_id": settings.OIDC_CLIENT_ID,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "scope": settings.OIDC_SCOPES,
        "state": "",
        "nonce": nonce,
    }
    state_kwargs: list[str] = [nonce]
    if pkce_enabled():
        verifier, challenge = generate_pkce_pair()
        params["code_challenge"] = challenge
        params["code_challenge_method"] = "S256"
        state_kwargs.append(verifier)
    params["state"] = make_state(*state_kwargs)
    query = "&".join(f"{k}={_urlquote(v)}" for k, v in params.items())
    return f"{endpoint}?{query}"


def _urlquote(v: str) -> str:
    from urllib.parse import quote
    return quote(v, safe="")


def exchange_code(code: str, code_verifier: str | None = None) -> dict:
    """تبادل کد → توکن‌ها → userinfo (با PKCE در صورت فراهم بودن verifier)."""
    conf = discover()
    token_endpoint = conf.get("token_endpoint")
    userinfo_endpoint = conf.get("userinfo_endpoint")
    if not token_endpoint or not userinfo_endpoint:
        raise OIDCError("token/userinfo endpoint در پیکربندی IdP یافت نشد")
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "client_id": settings.OIDC_CLIENT_ID,
    }
    if settings.OIDC_CLIENT_SECRET:
        data["client_secret"] = settings.OIDC_CLIENT_SECRET
    if code_verifier:
        data["code_verifier"] = code_verifier
    try:
        resp = httpx.post(token_endpoint, data=data, timeout=15.0)
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
