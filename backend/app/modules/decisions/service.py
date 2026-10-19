# -*- coding: utf-8 -*-
"""سرویس جدول تصمیم — ارزیابی با نسخه منتشرشده + اتصال به کانکتور و فرایند."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.decisions.engine import DecisionTable, DecisionError, evaluate_table
from app.modules.decisions.models import DecisionDefinition, DecisionVersion


def get_published_version(db: Session, key: str) -> DecisionVersion | None:
    d = db.scalar(select(DecisionDefinition).where(DecisionDefinition.key == key))
    if not d:
        return None
    return d.latest_published


def evaluate_by_key(db: Session, key: str, data: dict) -> dict:
    """ارزیابی با آخرین نسخه منتشرشده جدول تصمیم."""
    v = get_published_version(db, key)
    if not v:
        raise DecisionError(f"جدول تصمیم «{key}» نسخه منتشرشده ندارد")
    table = DecisionTable.from_schema(v.schema_json)
    result = evaluate_table(table, data)
    result["_decisionKey"] = key
    result["_decisionVersion"] = v.version
    return result


def validate_version_schema(schema: dict | None) -> list[str]:
    """اعتبارسنجی ساختاری — پیش از انتشار اجباری است."""
    try:
        table = DecisionTable.from_schema(schema)
    except DecisionError as e:
        return [str(e)]
    return table.validate()
