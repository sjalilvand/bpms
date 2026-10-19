# -*- coding: utf-8 -*-
"""موتور اعتبارسنجی فرم — مرجع نهایی پذیرش داده در سرور (سند §۱۳).

- مرورگر برای بازخورد سریع است؛ این ماژول مرجع نهایی است.
- محاسبات مهم (مانند جمع مبلغ) در سرور مجدداً محاسبه می‌شوند.
- ثبت موقت (partial) الزامی‌بودن را می‌پذیرد اما قواعد امنیتی را دور نمی‌زند.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.forms.persian import (
    normalize_digits, normalize_national_id, is_valid_national_id,
    normalize_mobile, is_valid_mobile, jalali_to_gregorian_str,
)
from app.modules.forms.safeeval import evaluate_formula, evaluate_condition

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")
MAX_SUBFORM_DEPTH = 3
MAX_SUBFORM_ROWS = 200

TEXTUAL_TYPES = {"text", "textarea", "richtext"}
NUMERIC_TYPES = {"number", "integer", "money", "percent"}
SELECT_TYPES = {"select", "multiselect", "checkgroup", "radio"}


class FormValidationResult:
    def __init__(self):
        self.errors: list[dict] = []
        self.cleaned: dict = {}

    def add(self, key: str, message: str):
        self.errors.append({"key": key, "message": message})

    @property
    def ok(self) -> bool:
        return not self.errors


def _load_subform_schema(db: Session, form_definition_id: int) -> dict | None:
    """واکشی آخرین نسخه منتشرشده زیرفرم (استفاده مجدد از فرم منتشرشده)."""
    from app.modules.forms.models import FormVersion
    fv = db.scalars(
        select(FormVersion)
        .where(FormVersion.form_id == form_definition_id, FormVersion.status == "published")
        .order_by(FormVersion.version.desc())
    ).first()
    return fv.schema_json if fv else None


def _is_visible(field: dict, data: dict) -> bool:
    cond = field.get("visibleIf")
    if not cond:
        return True
    return evaluate_condition(cond, lambda k: data.get(k))


def _lookup_allowed_values(db: Session, lookup_id: int) -> list:
    from app.modules.lookups.router import LookupItem
    rows = db.scalars(select(LookupItem).where(LookupItem.lookup_id == lookup_id)).all()
    return [r.id for r in rows]


def _option_values(field: dict) -> list:
    return [o.get("value") if isinstance(o, dict) else o for o in field.get("options") or []]


def validate_form_data(
    db: Session,
    schema: dict,
    data: dict,
    *,
    partial: bool = False,
    subform_depth: int = 0,
) -> FormValidationResult:
    """اعتبارسنجی و پاکسازی داده فرم. خروجی: errors + cleaned (نرمال‌شده برای ذخیره)."""
    result = FormValidationResult()
    if not isinstance(data, dict):
        data = {}
    all_fields = schema.get("fields", [])
    # گذر اول: فیلدهای عادی؛ گذر دوم: محاسباتی (به متغیرهای پاک‌شده همه فیلدها دسترسی دارند)
    ordered = [f for f in all_fields if f.get("type") != "calculated"] + \
              [f for f in all_fields if f.get("type") == "calculated"]
    for field in ordered:
        key = field.get("key")
        ftype = field.get("type", "text")
        if not key or ftype in ("title", "help", "divider", "summary"):
            continue
        if not _is_visible(field, data):
            continue
        raw = data.get(key, None)
        prefix = key

        # ---- ساختاری: زیرفرم ----
        if ftype in ("subform", "subform_single"):
            if subform_depth >= MAX_SUBFORM_DEPTH:
                result.add(prefix, "عمق تودرتویی زیرفرم بیش از حد مجاز است")
                continue
            sub_schema = _load_subform_schema(db, field.get("subformId")) if field.get("subformId") else None
            if sub_schema is None:
                result.add(prefix, "زیرفرم منتشرشده‌ای برای این فیلد یافت نشد")
                continue
            if ftype == "subform_single":
                if raw in (None, ""):
                    result.cleaned[key] = None
                    continue
                if not isinstance(raw, dict):
                    result.add(prefix, "مقدار زیرفرم تک‌نمونه‌ای باید شیء باشد")
                    continue
                rows = [raw]
            else:
                if raw is None:
                    raw = []
                if not isinstance(raw, list):
                    result.add(prefix, "مقدار زیرفرم تکرارشونده باید فهرست باشد")
                    continue
                rows = raw
                if not partial:
                    min_rows, max_rows = field.get("minRows"), field.get("maxRows")
                    if min_rows is not None and len(rows) < int(min_rows):
                        result.add(prefix, f"حداقل {min_rows} ردیف لازم است")
                    if max_rows is not None and len(rows) > int(max_rows):
                        result.add(prefix, f"حداکثر {max_rows} ردیف مجاز است")
                if len(rows) > MAX_SUBFORM_ROWS:
                    result.add(prefix, f"تعداد ردیف‌ها بیش از حد مجاز ({MAX_SUBFORM_ROWS}) است")
            cleaned_rows = []
            for idx, row in enumerate(rows[:MAX_SUBFORM_ROWS]):
                r = validate_form_data(db, sub_schema, row or {}, partial=partial, subform_depth=subform_depth + 1)
                if not r.ok:
                    for e in r.errors:
                        result.add(f"{prefix}[{idx}].{e['key']}", e["message"])
                cleaned_rows.append(r.cleaned)
            result.cleaned[key] = cleaned_rows[0] if ftype == "subform_single" else cleaned_rows
            continue

        # ---- محاسباتی: فرمول در سرور مجدداً محاسبه می‌شود ----
        if ftype == "calculated":
            formula = field.get("formula", "")
            # خواندن از مقادیر پاک‌شده (شامل زیرفرم و ردیف‌ها)؛ fallback به داده خام
            resolver = _make_resolver({**data, **result.cleaned})
            value = evaluate_formula(formula, resolver)
            result.cleaned[key] = value
            continue

        empty = raw in (None, "", [])
        if empty:
            if field.get("required") and not partial:
                result.add(prefix, f"«{field.get('label', key)}» الزامی است")
                result.cleaned[key] = _default_clean(raw, ftype)
            else:
                result.cleaned[key] = _default_clean(raw, ftype)
            continue

        # ---- انواع متنی ----
        if ftype in TEXTUAL_TYPES:
            v = normalize_digits(str(raw)) if ftype == "text" and field.get("digitsNormalize", True) else str(raw)
            v = v.strip()
            if field.get("minLength") and len(v) < int(field["minLength"]):
                result.add(prefix, f"حداقل {field['minLength']} نویسه لازم است")
            if field.get("maxLength") and len(v) > int(field["maxLength"]):
                result.add(prefix, f"حداکثر {field['maxLength']} نویسه مجاز است")
            if field.get("pattern"):
                try:
                    if not re.match(field["pattern"], v):
                        result.add(prefix, "قالب مقدار واردشده صحیح نیست")
                except re.error:
                    result.add(prefix, "الگوی تعریف‌شده فیلد نامعتبر است")
            result.cleaned[key] = v
            continue

        # ---- انواع ایرانی ----
        if ftype == "national_id":
            v = normalize_national_id(str(raw))
            if not is_valid_national_id(v):
                result.add(prefix, "کد ملی واردشده معتبر نیست")
            result.cleaned[key] = v
            continue

        if ftype == "mobile":
            v = normalize_mobile(str(raw))
            if not is_valid_mobile(v):
                result.add(prefix, "شماره موبایل باید با 09 شروع شده و ۱۱ رقم باشد")
            result.cleaned[key] = v
            continue

        if ftype == "email":
            v = str(raw).strip()
            if not EMAIL_RE.match(v):
                result.add(prefix, "نشانی ایمیل معتبر نیست")
            result.cleaned[key] = v
            continue

        # ---- عددی ----
        if ftype in NUMERIC_TYPES:
            try:
                if isinstance(raw, bool):
                    raise ValueError
                v = float(str(raw).replace(",", "")) if not isinstance(raw, (int, float)) else raw
                v = float(v)
            except (ValueError, TypeError):
                result.add(prefix, "مقدار عددی نامعتبر است")
                continue
            if ftype == "integer":
                if v != int(v):
                    result.add(prefix, "عدد صحیح وارد کنید")
                    v = int(v)
                else:
                    v = int(v)
            if field.get("min") is not None and v < float(field["min"]):
                result.add(prefix, f"حداقل مقدار مجاز {field['min']} است")
            if field.get("max") is not None and v > float(field["max"]):
                result.add(prefix, f"حداکثر مقدار مجاز {field['max']} است")
            dp = field.get("decimalPlaces")
            if dp is not None and ftype in ("number", "money", "percent"):
                v = round(v, int(dp))
            result.cleaned[key] = v
            continue

        # ---- زمان ----
        if ftype in ("date", "jalali_date"):
            v = jalali_to_gregorian_str(str(raw)) or str(raw).strip()
            if not DATE_RE.match(v):
                try:
                    from datetime import date as _date
                    _date.fromisoformat(v)
                except ValueError:
                    result.add(prefix, "تاریخ نامعتبر است")
                    continue
            for bound, msg in (("minDate", "تاریخ زودتر از حداقل مجاز است"), ("maxDate", "تاریخ دیرتر از حداکثر مجاز است")):
                if field.get(bound):
                    b = jalali_to_gregorian_str(str(field[bound])) or str(field[bound])
                    if DATE_RE.match(b) and (v < b if bound == "minDate" else v > b):
                        result.add(prefix, msg)
            result.cleaned[key] = v
            continue

        if ftype == "time":
            v = normalize_digits(str(raw)).strip()
            if not TIME_RE.match(v):
                result.add(prefix, "ساعت نامعتبر است (نمونه: 13:45)")
            result.cleaned[key] = v
            continue

        # ---- انتخابی ----
        if ftype in SELECT_TYPES:
            multiple = ftype in ("multiselect", "checkgroup")
            allowed = _lookup_allowed_values(db, field["lookupId"]) if field.get("lookupId") else _option_values(field)
            values = raw if isinstance(raw, list) else [raw]
            if not multiple and isinstance(raw, list):
                result.add(prefix, "این فیلد تنها یک گزینه می‌پذیرد")
                continue
            if multiple and not isinstance(raw, list):
                result.add(prefix, "این فیلد فهرست گزینه می‌پذیرد")
                continue
            norm: list = []
            for val in values:
                cv = _coerce_option_value(val, allowed)
                if allowed and cv not in allowed:
                    result.add(prefix, "گزینه انتخابی معتبر نیست")
                    norm = []
                    break
                norm.append(cv)
            if norm or not field.get("required"):
                result.cleaned[key] = norm if multiple else (norm[0] if norm else None)
            continue

        if ftype == "checkbox":
            result.cleaned[key] = bool(raw)
            continue

        # ---- سازمانی ----
        if ftype in ("user", "org_unit"):
            try:
                v = int(raw)
            except (ValueError, TypeError):
                result.add(prefix, "شناسه نامعتبر است")
                continue
            if ftype == "user":
                from app.modules.identity.models import User
                if not db.get(User, v):
                    result.add(prefix, "کاربر انتخابی یافت نشد")
            else:
                from app.modules.organization.models import OrganizationUnit
                if not db.get(OrganizationUnit, v):
                    result.add(prefix, "واحد سازمانی یافت نشد")
            result.cleaned[key] = v
            continue

        # ---- فایل ----
        if ftype in ("file", "image", "attachment_list"):
            # پیوست‌ها از مسیر کنترل‌شده /attachments مدیریت می‌شوند؛ مقدار فیلد شناسه پیوست است.
            if isinstance(raw, list):
                ids = []
                for x in raw:
                    try:
                        ids.append(int(x))
                    except (ValueError, TypeError):
                        result.add(prefix, "شناسه پیوست نامعتبر است")
                        break
                result.cleaned[key] = ids
            else:
                try:
                    result.cleaned[key] = int(raw)
                except (ValueError, TypeError):
                    result.add(prefix, "شناسه پیوست نامعتبر است")
            continue

        # سایر انواع: بدون تغییر
        result.cleaned[key] = raw

    # ---- مقایسه فیلدها ----
    for field in schema.get("fields", []):
        key, cf = field.get("key"), field.get("compareField")
        if not key or not cf:
            continue
        a, b = result.cleaned.get(key), data.get(cf)
        op = field.get("compareOp", "==")
        try:
            good = {
                "==": a == b, "!=": a != b,
                ">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b,
            }[op]
        except TypeError:
            good = False
        if not good and not (a in (None, "") and b in (None, "")):
            result.add(key, field.get("compareMessage") or f"مقدار باید با «{cf}» سازگار باشد")

    return result


def _default_clean(raw, ftype):
    if ftype in ("multiselect", "checkgroup"):
        return raw if isinstance(raw, list) else []
    if ftype == "checkbox":
        return bool(raw)
    return raw


def _coerce_option_value(val, allowed):
    """تطبیق نوع گزینه با مقادیر مجاز (شناسه عددی جدول پایه یا مقدار ثابت)."""
    if allowed and isinstance(allowed[0], int) and isinstance(val, str) and val.isdigit():
        return int(val)
    return val


def _make_resolver(data: dict) -> Callable[[str], Any]:
    def resolver(key: str):
        if key.startswith("__list__"):
            arr = data.get(key[len("__list__"):], [])
            return arr if isinstance(arr, list) else []
        return data.get(key)
    return resolver
