# -*- coding: utf-8 -*-
"""فاز ۵ — مدیریت یکپارچه‌سازی: کلیدهای سرویس بیرونی، مقصدهای Webhook و گزارش تحویل.

مجوز: integration.manage (مدیر سامانه) — رمز کلیدها یک‌بار در ساخت/چرخش نمایش داده می‌شود.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_perm
from app.modules.audit.service import log_action
from app.modules.external import service as ext
from app.modules.external.models import ExternalClient, WebhookDelivery, WebhookEndpoint
from app.modules.external.router import SCOPES

router = APIRouter()


class ClientIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    scopes: list[str] = []
    require_signature: bool = False
    rate_limit_per_min: int = Field(default=60, ge=1, le=10000)
    actor_username: str | None = None
    is_active: bool = True


class ClientUpdateIn(BaseModel):
    scopes: list[str] | None = None
    require_signature: bool | None = None
    rate_limit_per_min: int | None = Field(default=None, ge=1, le=10000)
    actor_username: str | None = None
    is_active: bool | None = None


class WebhookIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    events: list[str] = ["*"]
    is_active: bool = True


def client_out(c: ExternalClient, secret: str | None = None) -> dict:
    d = {
        "id": c.id, "name": c.name, "key_id": c.key_id, "scopes": c.scopes or [],
        "require_signature": c.require_signature, "rate_limit_per_min": c.rate_limit_per_min,
        "actor_username": c.actor_username, "is_active": c.is_active,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
    }
    if secret:
        d["key_secret"] = secret  # فقط در ساخت/چرخش
    return d


@router.get("/integrations/clients")
def list_clients(db: Session = Depends(get_db), user=Depends(require_perm("integration.manage"))):
    rows = db.scalars(select(ExternalClient).order_by(ExternalClient.id)).all()
    return {"items": [client_out(c) for c in rows], "available_scopes": SCOPES}


@router.post("/integrations/clients")
def create_client(body: ClientIn, db: Session = Depends(get_db),
                  user=Depends(require_perm("integration.manage")), request: Request = None):
    bad = [s for s in body.scopes if s != "*" and s not in SCOPES]
    if bad:
        raise HTTPException(400, f"دامنه‌های نامعتبر: {', '.join(bad)}")
    key_id, secret = ext.generate_client_credentials()
    c = ExternalClient(name=body.name, key_id=key_id, key_secret=secret, scopes=body.scopes,
                       require_signature=body.require_signature,
                       rate_limit_per_min=body.rate_limit_per_min,
                       actor_username=body.actor_username, is_active=body.is_active,
                       created_by_id=user.id)
    db.add(c)
    db.commit()
    log_action(db, user.id, "integration.client_created", "external_client", c.id, {"key_id": key_id}, request)
    return client_out(c, secret=secret)


@router.put("/integrations/clients/{cid}")
def update_client(cid: int, body: ClientUpdateIn, db: Session = Depends(get_db),
                  user=Depends(require_perm("integration.manage")), request: Request = None):
    c = db.get(ExternalClient, cid)
    if not c:
        raise HTTPException(404, "سرویس بیرونی یافت نشد")
    if body.scopes is not None:
        bad = [s for s in body.scopes if s != "*" and s not in SCOPES]
        if bad:
            raise HTTPException(400, f"دامنه‌های نامعتبر: {', '.join(bad)}")
        c.scopes = body.scopes
    if body.require_signature is not None:
        c.require_signature = body.require_signature
    if body.rate_limit_per_min is not None:
        c.rate_limit_per_min = body.rate_limit_per_min
    if body.actor_username is not None:
        c.actor_username = body.actor_username or None
    if body.is_active is not None:
        c.is_active = body.is_active
    db.commit()
    log_action(db, user.id, "integration.client_updated", "external_client", c.id, {}, request)
    return client_out(c)


@router.post("/integrations/clients/{cid}/rotate-secret")
def rotate_secret(cid: int, db: Session = Depends(get_db),
                  user=Depends(require_perm("integration.manage")), request: Request = None):
    c = db.get(ExternalClient, cid)
    if not c:
        raise HTTPException(404, "سرویس بیرونی یافت نشد")
    c.key_secret = secrets.token_hex(24)
    db.commit()
    log_action(db, user.id, "integration.secret_rotated", "external_client", c.id, {}, request)
    return {"key_id": c.key_id, "key_secret": c.key_secret}


# ---------------- Webhook ----------------
def webhook_out(w: WebhookEndpoint) -> dict:
    return {
        "id": w.id, "url": w.url, "events": w.events or [], "is_active": w.is_active,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


@router.get("/integrations/webhooks")
def list_webhooks(db: Session = Depends(get_db), user=Depends(require_perm("integration.manage"))):
    rows = db.scalars(select(WebhookEndpoint).order_by(WebhookEndpoint.id)).all()
    events = ["*", "instance.started", "instance.completed", "instance.cancelled",
              "task.created", "task.completed"]
    return {"items": [webhook_out(w) for w in rows], "available_events": events}


@router.post("/integrations/webhooks")
def create_webhook(body: WebhookIn, db: Session = Depends(get_db),
                   user=Depends(require_perm("integration.manage")), request: Request = None):
    if not body.url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "آدرس Webhook باید با http(s) شروع شود")
    w = WebhookEndpoint(url=body.url, secret=secrets.token_hex(24), events=body.events,
                        is_active=body.is_active, created_by_id=user.id)
    db.add(w)
    db.commit()
    log_action(db, user.id, "integration.webhook_created", "webhook_endpoint", w.id, {"url": w.url}, request)
    out = webhook_out(w)
    out["secret"] = w.secret  # یک‌بار نمایش
    return out


@router.delete("/integrations/webhooks/{wid}")
def delete_webhook(wid: int, db: Session = Depends(get_db),
                   user=Depends(require_perm("integration.manage")), request: Request = None):
    w = db.get(WebhookEndpoint, wid)
    if not w:
        raise HTTPException(404, "Webhook یافت نشد")
    db.delete(w)
    db.commit()
    log_action(db, user.id, "integration.webhook_deleted", "webhook_endpoint", wid, {}, request)
    return {"ok": True}


@router.get("/integrations/deliveries")
def list_deliveries(db: Session = Depends(get_db), user=Depends(require_perm("integration.manage")),
                    endpoint_id: int | None = None, page: int = 1, page_size: int = 20):
    stmt = select(WebhookDelivery).order_by(WebhookDelivery.id.desc())
    if endpoint_id:
        stmt = stmt.where(WebhookDelivery.endpoint_id == endpoint_id)
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{
        "id": d.id, "endpoint_id": d.endpoint_id, "event_type": d.event_type,
        "status": d.status, "attempts": d.attempts, "last_status_code": d.last_status_code,
        "last_error": d.last_error,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
    } for d in rows]}
