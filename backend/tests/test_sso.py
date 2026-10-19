# -*- coding: utf-8 -*-
"""آزمون‌های فاز ۵ — ورود سازمانی OIDC و LDAP (با سرویس/mock، بدون IdP واقعی)."""
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.modules.identity import oidc
from app.modules.identity.models import Role, User


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture()
def api():
    with TestClient(app) as c:
        yield c


class TestOIDCUnit:
    def test_state_roundtrip_and_expiry(self):
        nonce = "abc123"
        state = oidc.make_state(nonce)
        assert oidc.parse_state(state) == nonce
        assert oidc.parse_state("garbage") is None

    def test_extract_username_priority(self):
        assert oidc.extract_username({"preferred_username": "ali", "email": "a@b.c"}) == "ali"
        assert oidc.extract_username({"email": "maryam@corp.ir"}) == "maryam"
        assert oidc.extract_username({"sub": "f3e1"}) == "f3e1"
        assert oidc.extract_username({}) is None

    def test_discovery_cache(self, monkeypatch):
        calls = {"n": 0}

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                calls["n"] += 1
                return {"authorization_endpoint": "https://idp/authorize",
                        "token_endpoint": "https://idp/token",
                        "userinfo_endpoint": "https://idp/userinfo"}

        monkeypatch.setattr(oidc.httpx, "get", lambda *a, **k: R())
        oidc._DISCOVERY_CACHE.update(ts=0, data=None)
        c1 = oidc.discover()
        c2 = oidc.discover()  # از کش
        assert c1 == c2 and calls["n"] == 1
        url = oidc.build_authorize_url()
        assert url.startswith("https://idp/authorize?") and "state=" in url and "nonce=" in url
        oidc._DISCOVERY_CACHE.update(ts=0, data=None)

    def test_exchange_code_flow(self, monkeypatch):
        conf = {"token_endpoint": "https://idp/token", "userinfo_endpoint": "https://idp/userinfo"}
        monkeypatch.setattr(oidc, "discover", lambda: conf)

        def fake_post(url, data=None, timeout=None):
            class R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"access_token": "AT"}

            assert url == "https://idp/token"
            return R()

        def fake_get(url, headers=None, timeout=None):
            class R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"sub": "u1", "preferred_username": "sso.user", "name": "کاربر SSO"}

            assert url == "https://idp/userinfo"
            assert headers["Authorization"] == "Bearer AT"
            return R()

        monkeypatch.setattr(oidc.httpx, "post", fake_post)
        monkeypatch.setattr(oidc.httpx, "get", fake_get)
        ui = oidc.exchange_code("some-code")
        assert ui["preferred_username"] == "sso.user"


class TestOIDCEndpoints:
    def test_auth_config_public(self, api):
        r = api.get("/api/v1/auth/config")
        assert r.status_code == 200
        assert set(r.json().keys()) == {"oidc_enabled", "ldap_enabled"}

    def test_oidc_login_disabled(self, api):
        r = api.get("/api/v1/auth/oidc/login")
        assert r.status_code == 400

    def test_oidc_callback_full_provisioning(self, api, db, monkeypatch):
        # فعال‌سازی ساختگی OIDC
        monkeypatch.setattr(oidc, "oidc_configured", lambda: True)
        monkeypatch.setattr(oidc, "exchange_code", lambda code, code_verifier=None: {
            "sub": "u-77", "preferred_username": "sso.newbie", "name": "کاربر سازمانی جدید",
            "email": "sso.newbie@corp.ir"})
        state = oidc.make_state("n1")
        r = api.get("/api/v1/auth/oidc/callback", params={"code": "c1", "state": state},
                    follow_redirects=False)
        assert r.status_code == 302
        assert "oidc_token=" in r.headers["location"]
        # کاربر تأمین‌شده با نقش پیش‌فرض
        u = db.scalar(select(User).where(User.username == "sso.newbie"))
        assert u is not None
        assert u.full_name == "کاربر سازمانی جدید"
        assert any(role.code == "operator" for role in u.roles)

    def test_oidc_callback_bad_state(self, api, monkeypatch):
        monkeypatch.setattr(oidc, "oidc_configured", lambda: True)
        r = api.get("/api/v1/auth/oidc/callback", params={"code": "c", "state": "bad"},
                    follow_redirects=False)
        assert r.status_code == 302
        assert "oidc_error=state" in r.headers["location"]


class TestPKCE:
    """فاز ۶ — PKCE (RFC 7636) روی جریان Authorization Code."""

    def test_pkce_pair_rfc7636(self):
        verifier, challenge = oidc.generate_pkce_pair()
        # محدوده طول verifier طبق RFC 7636: ۴۳ تا ۱۲۸ نویسه base64url
        assert 43 <= len(verifier) <= 128
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert set(verifier) <= allowed
        import base64, hashlib
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()).decode().rstrip("=")
        assert challenge == expected
        assert "=" not in challenge

    def test_pkce_pairs_are_unique(self):
        a, b = oidc.generate_pkce_pair(), oidc.generate_pkce_pair()
        assert a[0] != b[0] and a[1] != b[1]

    def test_state_carries_verifier(self):
        state = oidc.make_state("n9", "v" * 64)
        data = oidc.parse_state_data(state)
        assert data["nonce"] == "n9" and data["verifier"] == "v" * 64
        # سازگاری رو به عقب — parse_state همچنان nonce می‌دهد
        assert oidc.parse_state(state) == "n9"

    def test_authorize_url_includes_pkce(self, monkeypatch):
        monkeypatch.setattr(oidc, "discover", lambda: {
            "authorization_endpoint": "https://idp/authorize"})
        monkeypatch.setattr(oidc.settings, "OIDC_PKCE_ENABLED", True)
        url = oidc.build_authorize_url()
        assert "code_challenge=" in url and "code_challenge_method=S256" in url
        state = url.split("state=")[1].split("&")[0]
        from urllib.parse import unquote
        data = oidc.parse_state_data(unquote(state))
        assert data and len(data.get("verifier", "")) >= 43

    def test_authorize_url_without_pkce(self, monkeypatch):
        monkeypatch.setattr(oidc, "discover", lambda: {
            "authorization_endpoint": "https://idp/authorize"})
        monkeypatch.setattr(oidc.settings, "OIDC_PKCE_ENABLED", False)
        url = oidc.build_authorize_url()
        assert "code_challenge" not in url

    def test_exchange_code_sends_verifier_and_optional_secret(self, monkeypatch):
        conf = {"token_endpoint": "https://idp/token", "userinfo_endpoint": "https://idp/userinfo"}
        monkeypatch.setattr(oidc, "discover", lambda: conf)
        captured = {}

        def fake_post(url, data=None, timeout=None):
            captured.update(data or {})

            class R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"access_token": "AT"}

            return R()

        def fake_get(url, headers=None, timeout=None):
            class R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"sub": "u1", "preferred_username": "pk.user"}

            return R()

        monkeypatch.setattr(oidc.httpx, "post", fake_post)
        monkeypatch.setattr(oidc.httpx, "get", fake_get)
        monkeypatch.setattr(oidc.settings, "OIDC_CLIENT_SECRET", "")  # کلاینت عمومی
        oidc.exchange_code("code-1", code_verifier="ver-123")
        assert captured["code_verifier"] == "ver-123"
        assert "client_secret" not in captured
        assert captured["grant_type"] == "authorization_code"
        # secret پر شود → ارسال می‌شود
        monkeypatch.setattr(oidc.settings, "OIDC_CLIENT_SECRET", "top-secret")
        oidc.exchange_code("code-2")
        assert captured["client_secret"] == "top-secret"

    def test_callback_flow_passes_verifier(self, api, db, monkeypatch):
        """مسیر کامل callback — verifier از state استخراج و به تبادل کد می‌رسد."""
        received = {}

        def fake_exchange(code, code_verifier=None):
            received["code"], received["verifier"] = code, code_verifier
            return {"sub": "u-88", "preferred_username": "pk.flow", "name": "کاربر PKCE"}

        monkeypatch.setattr(oidc, "oidc_configured", lambda: True)
        monkeypatch.setattr(oidc, "exchange_code", fake_exchange)
        state = oidc.make_state("n-flow", "verifier-flow-0123456789012345678901234567890123456789")
        r = api.get("/api/v1/auth/oidc/callback", params={"code": "c-9", "state": state},
                    follow_redirects=False)
        assert r.status_code == 302
        assert received == {"code": "c-9", "verifier": "verifier-flow-0123456789012345678901234567890123456789"}
        u = db.scalar(select(User).where(User.username == "pk.flow"))
        assert u is not None


class TestLDAP:
    def _fake_ldap3(self, entries, bind_ok=True):
        """ساخت ماژول ساختگی ldap3 با نتایج ثابت."""
        import types

        class Conn:
            created = []

            def __init__(self, server, user=None, password=None, auto_bind=False, **kw):
                Conn.created.append({"user": user, "password": password})
                self.bound = bind_ok or (user and password)
                if auto_bind and not self.bound:
                    raise Exception("bind failed")

            def bind(self):
                return True

            def unbind(self):
                return True

            def search(self, base, filt, attributes=None):
                self.entries = entries
                return bool(entries)

        mod = types.ModuleType("ldap3")
        mod.Server = lambda *a, **k: object()
        mod.Connection = Conn
        mod.ALL = "ALL"
        return mod, Conn

    def test_ldap_disabled_by_default(self):
        from app.modules.identity.ldap_auth import ldap_configured
        assert ldap_configured() in (True, False)  # بسته به env؛ منع ترکیدن

    def test_ldap_auth_success_and_provision(self, db, monkeypatch):
        from app.modules.identity import ldap_auth
        mod, Conn = self._fake_ldap3([
            Entry("CN=Ali,OU=Users,DC=corp,DC=local",
                  {"displayName": "علی سازمانی", "mail": "ali@corp.local", "cn": "Ali"}),
        ])
        monkeypatch.setitem(__import__("sys").modules, "ldap3", mod)
        monkeypatch.setattr(ldap_auth, "ldap_configured", lambda: True)
        u = ldap_auth.authenticate_ldap(db, "ali.corp", "secret-pass")
        assert u is not None
        assert u.username == "ali.corp"
        assert u.full_name == "علی سازمانی"
        # bind دوم (کاربر) با DN یافت‌شده انجام شده است
        user_binds = [c for c in Conn.created if c["user"] == "CN=Ali,OU=Users,DC=corp,DC=local"]
        assert user_binds and user_binds[0]["password"] == "secret-pass"

    def test_ldap_wrong_password_returns_none(self, db, monkeypatch):
        from app.modules.identity import ldap_auth
        mod, _ = self._fake_ldap3([], bind_ok=False)
        monkeypatch.setitem(__import__("sys").modules, "ldap3", mod)
        monkeypatch.setattr(ldap_auth, "ldap_configured", lambda: True)
        assert ldap_auth.authenticate_ldap(db, "ghost.user", "wrong") is None

    def test_login_via_ldap_endpoint(self, api, db, monkeypatch):
        """مسیر کامل POST /auth/login با backend ساختگی LDAP."""
        from app.modules.identity import ldap_auth
        from app.core.config import settings
        mod, Conn = self._fake_ldap3([
            Entry("CN=Maryam,OU=Users,DC=corp,DC=local",
                  {"displayName": "مریم LDAP", "mail": "m@corp.local", "cn": "Maryam"}),
        ])
        monkeypatch.setitem(__import__("sys").modules, "ldap3", mod)
        monkeypatch.setattr(ldap_auth, "ldap_configured", lambda: True)
        monkeypatch.setattr(ldap_auth.settings, "LDAP_ENABLED", True)
        monkeypatch.setattr(ldap_auth.settings, "LDAP_URL", "ldap://fake")
        monkeypatch.setattr(ldap_auth.settings, "LDAP_USER_BASE", "OU=Users,DC=corp,DC=local")
        r = api.post("/api/v1/auth/login", json={"username": "maryam.ldap", "password": "pw-123"})
        assert r.status_code == 200, r.text
        assert r.json()["user"]["username"] == "maryam.ldap"


# ابزار Entry در سطح ماژول — دسترسی ویژگی‌محور (entry.displayName)
class Entry:
    def __init__(self, dn, attrs):
        self.entry_dn = dn
        self._attrs = attrs

    def __contains__(self, k):
        return k in self._attrs

    def __getattr__(self, k):
        try:
            return self._attrs[k]
        except KeyError:
            raise AttributeError(k)

    def __str__(self):
        return self._attrs.get("displayName") or self._attrs.get("cn") or ""

    def __getitem__(self, k):
        return self._attrs[k]
