# -*- coding: utf-8 -*-
"""API شرط‌ساز بصری — تجزیه، رندر، ارزیابی آزمایشی و متغیرهای عبارت شرط.

این سرویس توسط ویرایشگر بصری طراح فرایند استفاده می‌شود:
- /conditions/parse    → عبارت پایتونی به ساختار بصری (برای بازکردن شرط موجود در نمودار)
- /conditions/render   → ساختار بصری به عبارت پایتونی (منبع حقیقت رندر)
- /conditions/evaluate → آزمایش شرط روی داده نمونه پیش از اعمال روی جریان
- /conditions/variables→ فهرست متغیرهای ارجاع‌شده در عبارت
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.identity.models import User
from app.modules.conditions import parser

router = APIRouter()


class ParseIn(BaseModel):
    expression: str


class RenderIn(BaseModel):
    structure: dict


class EvaluateIn(BaseModel):
    expression: str = ""
    structure: dict | None = None
    data: dict = {}


@router.post("/conditions/parse")
def parse_condition(body: ParseIn, db=Depends(get_db), user: User = Depends(get_current_user)):
    try:
        struct = parser.parse(body.expression)
    except parser.ConditionError as e:
        return {"ok": False, "errors": [str(e)], "structure": None, "expression": body.expression}
    return {
        "ok": True, "errors": [], "structure": struct,
        "expression": parser.render(struct),
        "variables": parser.extract_variables(body.expression),
    }


@router.post("/conditions/render")
def render_condition(body: RenderIn, db=Depends(get_db), user: User = Depends(get_current_user)):
    errors = parser.validate_structure(body.structure)
    if errors:
        return {"ok": False, "errors": errors, "expression": ""}
    try:
        expr = parser.render(body.structure)
    except parser.ConditionError as e:
        return {"ok": False, "errors": [str(e)], "expression": ""}
    return {"ok": True, "errors": [], "expression": expr}


@router.post("/conditions/evaluate")
def evaluate_condition(body: EvaluateIn, db=Depends(get_db), user: User = Depends(get_current_user)):
    expr = body.expression
    if not expr and body.structure is not None:
        errors = parser.validate_structure(body.structure)
        if errors:
            return {"ok": False, "errors": errors, "result": None}
        try:
            expr = parser.render(body.structure)
        except parser.ConditionError as e:
            return {"ok": False, "errors": [str(e)], "result": None}
    if not expr.strip():
        return {"ok": False, "errors": ["شرط خالی است"], "result": None}
    try:
        result = parser.evaluate(expr, body.data)
    except parser.ConditionError as e:
        return {"ok": False, "errors": [str(e)], "result": None}
    return {"ok": True, "errors": [], "result": result, "expression": expr}


@router.post("/conditions/variables")
def condition_variables(body: ParseIn, db=Depends(get_db), user: User = Depends(get_current_user)):
    try:
        parser.parse(body.expression)
    except parser.ConditionError as e:
        return {"ok": False, "errors": [str(e)], "variables": []}
    return {"ok": True, "errors": [], "variables": parser.extract_variables(body.expression)}
