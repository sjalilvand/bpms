# -*- coding: utf-8 -*-
"""APIهای هویت: ورود، کاربر جاری، ورود سازمانی OIDC، LDAP، مدیریت کاربران و نقش‌ها."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, has_permission, require_perm
from app.core.security import create_access_token, verify_password, hash_password
from app.modules.identity.models import Role, User, utcnow
from app.modules.audit.service import log_action

router = APIRouter()

ALL_PERMISSIONS = [
    "form.view", "form.manage", "form.publish",
    "process.view", "process.manage", "process.publish", "process.start",
    "task.claim", "task.complete", "task.delegate",
    "monitor.view", "audit.view",
    "lookup.manage", "org.manage", "user.manage", "instance.manage",
    "decision.view", "decision.manage",
    "calendar.view", "calendar.manage",
    "integration.manage",  # فاز ۵ — مدیریت کلید سرویس بیرونی و Webhook
]


# ---------- Schemas ----------
class LoginIn(BaseModel):
    username: str
    password: str


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str | None = Field(default=None, min_length=6, max_length=100)
    full_name: str = Field(min_length=2, max_length=120)
    email: str | None = None
    mobile: str | None = None
    org_unit_id: int | None = None
    manager_id: int | None = None
    role_ids: list[int] = []
    is_active: bool = True
    is_superadmin: bool = False


class RoleIn(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    title: str = Field(min_length=2, max_length=100)
    description: str = ""
    permissions: list[str] = []


def user_out(u: User):
    return {
        "id": u.id, "username": u.username, "full_name": u.full_name,
        "email": u.email, "mobile": u.mobile, "org_unit_id": u.org_unit_id,
        "manager_id": u.manager_id, "is_active": u.is_active,
        "is_superadmin": u.is_superadmin,
        "roles": [{"id": r.id, "code": r.code, "title": r.title, "permissions": r.permissions} for r in u.roles],
    }


# ---------- Auth ----------
@router.get("/auth/config")
def auth_config():
    """پیکربندی عمومی صفحه ورود (بدون احراز هویت) — فاز ۵."""
    from app.modules.identity.oidc import oidc_configured
    from app.modules.identity.ldap_auth import ldap_configured
    return {"oidc_enabled": oidc_configured(), "ldap_enabled": ldap_configured()}


@router.get("/auth/oidc/login")
def oidc_login():
    """شروع جریان مجاز OIDC — هدایت مرورگر به IdP سازمانی."""
    from app.modules.identity.oidc import oidc_configured, build_authorize_url, OIDCError
    if not oidc_configured():
        raise HTTPException(400, "ورود سازمانی OIDC فعال نشده است")
    try:
        return RedirectResponse(build_authorize_url(), status_code=302)
    except OIDCError as e:
        raise HTTPException(502, str(e))


@router.get("/auth/oidc/callback")
def oidc_callback(code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db), request: Request = None):
    """تبادل کد، تأمین کاربر و هدایت به رابط کاربری با توکن BPMS."""
    from app.modules.identity import oidc as oidc_mod
    from app.modules.identity.ldap_auth import provision_user
    frontend = (settings.OIDC_REDIRECT_URI or "").rsplit("/api/", 1)[0] or "/"
    if error:
        return RedirectResponse(f"{frontend}/login?oidc_error={error}", status_code=302)
    nonce = oidc_mod.parse_state(state)
    if not nonce or not code:
        return RedirectResponse(f"{frontend}/login?oidc_error=state", status_code=302)
    try:
        userinfo = oidc_mod.exchange_code(code)
    except oidc_mod.OIDCError as e:
        return RedirectResponse(f"{frontend}/login?oidc_error=exchange", status_code=302)
    username = oidc_mod.extract_username(userinfo)
    if not username:
        return RedirectResponse(f"{frontend}/login?oidc_error=identity", status_code=302)
    u = provision_user(db, username, str(userinfo.get("name") or username), userinfo.get("email"))
    if not u.is_active:
        return RedirectResponse(f"{frontend}/login?oidc_error=inactive", status_code=302)
    token = create_access_token(str(u.id), {"username": u.username})
    log_action(db, u.id, "login.oidc", "user", u.id, {"username": u.username}, request)
    db.commit()
    return RedirectResponse(f"{frontend}/login?oidc_token={token}", status_code=302)


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username.strip()))
    ok = False
    if user and user.password_hash and not user.password_hash.startswith("!"):
        ok = verify_password(body.password, user.password_hash)
    if not ok:
        # فاز ۵: تلاش LDAP در صورت فعال بودن — کاربر محلی یافت/تأمین می‌شود
        from app.modules.identity.ldap_auth import ldap_configured, authenticate_ldap
        if ldap_configured():
            try:
                user = authenticate_ldap(db, body.username.strip(), body.password)
                ok = user is not None and user.is_active
                if ok:
                    db.commit()
            except Exception:
                ok = False
    if not ok or not user:
        log_action(db, None, "login.failed", "user", None, {"username": body.username}, request)
        raise HTTPException(status_code=401, detail="نام کاربری یا گذرواژه نادرست است")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="حساب کاربری غیرفعال است")
    token = create_access_token(str(user.id), {"username": user.username})
    log_action(db, user.id, "login.success", "user", user.id, {}, request)
    return {"access_token": token, "token_type": "bearer", "user": user_out(user)}


@router.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.get("/auth/permissions")
def my_permissions(user: User = Depends(get_current_user)):
    if user.is_superadmin:
        return {"permissions": ["*"]}
    perms: set[str] = set()
    for r in user.roles:
        perms.update(r.permissions or [])
    return {"permissions": sorted(perms)}


# ---------- Users ----------
@router.get("/users")
def list_users(db: Session = Depends(get_db), user: User = Depends(get_current_user),
               q: str = "", page: int = 1, page_size: int = 50):
    stmt = select(User)
    if q:
        stmt = stmt.where(or_(User.full_name.contains(q), User.username.contains(q)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(User.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [user_out(u) for u in rows], "total": total}


@router.post("/users")
def create_user(body: UserIn, db: Session = Depends(get_db),
                user: User = Depends(require_perm("user.manage")), request: Request = None):
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(400, "نام کاربری تکراری است")
    if not body.password:
        raise HTTPException(400, "گذرواژه الزامی است")
    u = User(username=body.username.strip(), password_hash=hash_password(body.password),
             full_name=body.full_name, email=body.email, mobile=body.mobile,
             org_unit_id=body.org_unit_id, manager_id=body.manager_id,
             is_active=body.is_active, is_superadmin=body.is_superadmin)
    for rid in body.role_ids:
        r = db.get(Role, rid)
        if r:
            u.roles.append(r)
    db.add(u)
    db.commit()
    log_action(db, user.id, "user.created", "user", u.id, {"username": u.username}, request)
    return user_out(u)


@router.put("/users/{uid}")
def update_user(uid: int, body: UserIn, db: Session = Depends(get_db),
                user: User = Depends(require_perm("user.manage")), request: Request = None):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "کاربر یافت نشد")
    u.full_name, u.email, u.mobile = body.full_name, body.email, body.mobile
    u.org_unit_id, u.manager_id = body.org_unit_id, body.manager_id
    u.is_active, u.is_superadmin = body.is_active, body.is_superadmin
    if body.password:
        u.password_hash = hash_password(body.password)
    u.roles = [r for r in (db.get(Role, rid) for rid in body.role_ids) if r]
    db.commit()
    log_action(db, user.id, "user.updated", "user", u.id, {}, request)
    return user_out(u)


# ---------- Roles ----------
@router.get("/roles")
def list_roles(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(Role).order_by(Role.id)).all()
    return {"items": [{"id": r.id, "code": r.code, "title": r.title,
                       "description": r.description, "permissions": r.permissions} for r in rows]}


@router.post("/roles")
def create_role(body: RoleIn, db: Session = Depends(get_db),
                user: User = Depends(require_perm("user.manage")), request: Request = None):
    if db.scalar(select(Role).where(Role.code == body.code)):
        raise HTTPException(400, "کد نقش تکراری است")
    r = Role(code=body.code, title=body.title, description=body.description, permissions=body.permissions)
    db.add(r)
    db.commit()
    log_action(db, user.id, "role.created", "role", r.id, {"code": r.code}, request)
    return {"id": r.id}


@router.get("/permissions")
def list_permissions(user: User = Depends(get_current_user)):
    return {"items": ALL_PERMISSIONS}
