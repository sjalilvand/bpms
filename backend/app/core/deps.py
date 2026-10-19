# -*- coding: utf-8 -*-
"""وابستگی‌های مشترک API: نشست دیتابیس، کاربر جاری و کنترل مجوز."""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.modules.identity.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="نشست نامعتبر است؛ دوباره وارد شوید")
    if creds is None:
        raise exc
    payload = decode_access_token(creds.credentials)
    if not payload or "sub" not in payload:
        raise exc
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise exc
    return user


class PermissionChecker:
    """کنترل دسترسی نقش‌محور — مجوزها باید صریح باشند."""

    def __init__(self, permission: str):
        self.permission = permission

    def __call__(self, request: Request, user: User = Depends(get_current_user)) -> User:
        if user.is_superadmin or has_permission(user, self.permission):
            return user
        raise HTTPException(status_code=403, detail=f"دسترسی لازم «{self.permission}» را ندارید")


def has_permission(user: User, permission: str) -> bool:
    for role in user.roles:
        perms = role.permissions or []
        if "*" in perms or permission in perms:
            # مجوز والد: user.manage شامل user.manage.self نیست؛ تطبیق ساده
            return True
        # اجازه wildcard بخشی: form.* پوشش form.view
        for p in perms:
            if p.endswith(".*") and permission.startswith(p[:-1]):
                return True
    return False


def require_perm(permission: str):
    return PermissionChecker(permission)
