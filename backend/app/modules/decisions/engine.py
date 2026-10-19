# -*- coding: utf-8 -*-
"""ارزیاب جدول تصمیم (DMN سبک) — امن، بدون eval/exec.

قرارداد عبارت ورودی (InputEntry):
- خالی یا "-"            → هر مقدار (Wildcard)
- "> 100" ، "<= 50"      → مقایسه عددی
- "== 'خرید'" ، "!= 3"   → تساوی/نابرابری (رشته با کوتیشن)
- "between 10..20"       → بازه بسته عددی
- "in a,b,c" یا "in 'a','b'" → عضویت در مجموعه
- مقدار ساده (عدد/رشته/true/false) → تساوی مستقیم

سیاست‌های برخورد (Hit Policy):
- FIRST    : نخستین قاعده منطبق (به ترتیب فهرست)
- UNIQUE   : فقط یک قاعده باید منطبق شود؛ بیش از یکی = خطای «تضاد»
- ANY      : خروجی قواعد منطبق باید یکسان باشد؛ وگرنه خطا
- PRIORITY : مقادیر خروجی اولین خروجی، بر اساس اولویت تعریف‌شده، بهترین انتخاب می‌شود
- COLLECT  : همه خروجی‌ها به‌صورت فهرست بازگردانده می‌شود
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.modules.forms.safeeval import evaluate_formula
from app.modules.decisions.models import HIT_POLICIES


class DecisionError(Exception):
    """خطای معنایی جدول تصمیم (اعتبارسنجی یا تضاد قواعد)."""


@dataclass
class DecisionTable:
    hit_policy: str = "FIRST"
    inputs: list[dict] = field(default_factory=list)
    outputs: list[dict] = field(default_factory=list)
    rules: list[dict] = field(default_factory=list)

    @classmethod
    def from_schema(cls, schema: dict | None) -> "DecisionTable":
        s = schema or {}
        hp = str(s.get("hitPolicy") or "FIRST").upper()
        if hp not in HIT_POLICIES:
            raise DecisionError(f"سیاست برخورد «{hp}» پشتیبانی نمی‌شود")
        return cls(
            hit_policy=hp,
            inputs=list(s.get("inputs") or []),
            outputs=list(s.get("outputs") or []),
            rules=[r for r in (s.get("rules") or []) if r.get("enabled", True)],
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        input_names = [i.get("name") for i in self.inputs]
        output_names = [o.get("name") for o in self.outputs]
        if not self.inputs:
            errors.append("حداقل یک ورودی لازم است")
        if not self.outputs:
            errors.append("حداقل یک خروجی لازم است")
        if len(set(input_names)) != len(input_names):
            errors.append("نام ورودی‌های تکراری مجاز نیست")
        if len(set(output_names)) != len(output_names):
            errors.append("نام خروجی‌های تکراری مجاز نیست")
        if not self.rules:
            errors.append("حداقل یک قاعده لازم است")
        for idx, rule in enumerate(self.rules, start=1):
            rid = rule.get("id") or f"rule-{idx}"
            ie = rule.get("inputEntries") or {}
            oe = rule.get("outputEntries") or {}
            unknown_in = [k for k in ie if k not in input_names]
            unknown_out = [k for k in oe if k not in output_names]
            if unknown_in:
                errors.append(f"قاعده «{rid}»: ورودی ناشناس {unknown_in}")
            if unknown_out:
                errors.append(f"قاعده «{rid}»: خروجی ناشناس {unknown_out}")
            if not oe:
                errors.append(f"قاعده «{rid}»: خروجی تعیین نشده است")
            for name, expr in ie.items():
                if expr in (None, "", "-"):
                    continue
                try:
                    _compile_entry(str(expr))
                except DecisionError as e:
                    errors.append(f"قاعده «{rid}» / ورودی «{name}»: {e}")
        if self.hit_policy in ("UNIQUE", "ANY"):
            # تشخیص استاتیک هم‌پوشانی قواعد با ورودی‌های کامل ثابت (بدون Wildcard)
            signatures: dict[tuple, list[str]] = {}
            for rule in self.rules:
                sig = tuple(sorted((k, str(v)) for k, v in (rule.get("inputEntries") or {}).items()))
                signatures.setdefault(sig, []).append(rule.get("id") or "?")
            for sig, rids in signatures.items():
                if len(rids) > 1 and self.hit_policy == "UNIQUE" and all(v not in ("", "-", None) for _, v in sig):
                    errors.append(f"سیاست UNIQUE: قواعد {rids} ورودی یکسان دارند")
        return errors


# ---------------- تحلیل و ارزیابی عبارت ورودی ----------------
_CMP_RE = re.compile(r"^\s*(>=|<=|==|!=|>|<)\s*(.+?)\s*$")
_BETWEEN_RE = re.compile(r"^\s*between\s+(\S+)\s*\.\.\s*(\S+)\s*$", re.IGNORECASE)
_IN_RE = re.compile(r"^\s*in\s+(.+)$", re.IGNORECASE | re.DOTALL)


def _to_number(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip().replace(",", "")
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return v


def _compile_entry(expr: str):
    """عبارت را به یک گزاره ارزیاب تبدیل می‌کند؛ خروجی: callable(value)->bool."""
    if expr is None or str(expr).strip() in ("", "-"):
        return lambda v: True
    text = str(expr).strip()

    m = _BETWEEN_RE.match(text)
    if m:
        lo_raw, hi_raw = m.group(1), m.group(2)
        try:
            lo, hi = _to_number(lo_raw), _to_number(hi_raw)
        except Exception:
            raise DecisionError(f"بازه نامعتبر: {text}")
        return lambda v: v is not None and v != "" and lo <= _to_number(v) <= hi

    m = _IN_RE.match(text)
    if m:
        parts = [p.strip().strip("'\"") for p in m.group(1).split(",") if p.strip()]
        nums = {p: _to_number(p) for p in parts}
        return lambda v: str(v).strip().strip("'\"") in parts or _to_number(v) in [nums[p] for p in parts]

    # عبارت‌های ناقص/بدشکل که با کلیدواژه‌ها شروع می‌شوند باید در اعتبارسنجی رد شوند
    low = text.lower()
    if low.startswith("between"):
        raise DecisionError(f"بازه نامعتبر (قالب صحیح: between 10..20): {text}")
    if low.startswith("in "):
        raise DecisionError(f"مجموعه ورودی نامعتبر (قالب صحیح: in a,b,c): {text}")

    m = _CMP_RE.match(text)
    if m:
        op, operand_raw = m.group(1), m.group(2).strip()
        operand = _to_number(operand_raw.strip("'\""))
        if isinstance(operand, str) and not (operand_raw.startswith("'") or operand_raw.startswith('"')):
            # رشته بدون کوتیشن — همان مقدار
            operand = operand_raw
        if op == "==":
            return lambda v: _loose_eq(v, operand)
        if op == "!=":
            return lambda v: not _loose_eq(v, operand)
        return lambda v: _compare(v, op, operand)

    if re.match(r"^(>=|<=|==|!=|>|<)", text):
        raise DecisionError(f"عبارت مقایسه نامعتبر: {text}")

    # مقدار ساده: true/false/عدد/رشته
    if low in ("true", "false"):
        want = low == "true"
        return lambda v: bool(v) is want
    if re.match(r"^-?\d+(\.\d+)?$", text):
        return lambda v: _loose_eq(v, _to_number(text))
    return lambda v: _loose_eq(v, text.strip("'\""))


def _loose_eq(a, b) -> bool:
    if a is None or a == "":
        return False
    if isinstance(a, str) and not isinstance(b, str):
        try:
            return _to_number(a) == b
        except Exception:
            return False
    return a == b or str(a) == str(b)


def _compare(v, op: str, operand) -> bool:
    if v is None or v == "":
        return False
    try:
        a, b = _to_number(v), _to_number(operand)
        if isinstance(a, str) or isinstance(b, str):
            a, b = str(v), str(operand)
    except Exception:
        a, b = str(v), str(operand)
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    return False


def _resolver_factory(data: dict):
    def resolver(name: str):
        if name in data:
            return data[name]
        return None
    return resolver


def _entry_matches(entry: str, value, data: dict) -> bool:
    """عبارت ورودی؛ اگر با ارزیاب امن قابل تحلیل بود از آن استفاده می‌کنیم (پشتیبانی && و ||)."""
    text = str(entry).strip()
    if text in ("", "-"):
        return True
    # ترکیب منطقی ساده: هر دو سمت && یا || جداگانه ارزیابی می‌شوند
    if "&&" in text:
        return all(_entry_matches(part, value, data) for part in text.split("&&"))
    if "||" in text:
        return any(_entry_matches(part, value, data) for part in text.split("||"))
    pred = _compile_entry(text)
    try:
        return bool(pred(value))
    except Exception:
        return False


def evaluate_table(table: DecisionTable, data: dict) -> dict:
    """ارزیابی جدول با داده ورودی.

    خروجی:
    - COLLECT: {"results": [ {output: value, ...}, ... ], "matched": n}
    - بقیه:    {output: value, ...} + کلیدهای "_matchedRule"
    """
    input_names = [i.get("name") for i in table.inputs]
    output_names = [o.get("name") for o in table.outputs]
    missing = [n for n in input_names if n not in data]
    if missing:
        raise DecisionError(f"داده ورودی «{missing[0]}» ارسال نشده است")

    matched: list[tuple[dict, dict]] = []  # (rule, outputs)
    for idx, rule in enumerate(table.rules, start=1):
        ie = rule.get("inputEntries") or {}
        ok = True
        for name in input_names:
            expr = ie.get(name)
            if expr in (None, "", "-"):
                continue
            if not _entry_matches(str(expr), data.get(name), data):
                ok = False
                break
        if ok:
            oe = {}
            for name in output_names:
                v = (rule.get("outputEntries") or {}).get(name)
                oe[name] = v if v is not None else _output_default(table, name)
            matched.append((rule, oe))

    if table.hit_policy == "COLLECT":
        return {"results": [oe for _, oe in matched], "matched": len(matched)}

    if not matched:
        # مقدار پیش‌فرض خروجی‌ها در صورت تعریف
        defaults = {n: _output_default(table, n) for n in output_names}
        return {**defaults, "_matchedRule": None}

    if table.hit_policy == "UNIQUE" and len(matched) > 1:
        rids = [r.get("id") or f"rule-{i + 1}" for i, (r, _) in enumerate(matched)]
        raise DecisionError(f"سیاست UNIQUE نقض شد: بیش از یک قاعده منطبق شد ({', '.join(rids)})")

    if table.hit_policy == "ANY":
        first = matched[0][1]
        for _, oe in matched[1:]:
            if oe != first:
                raise DecisionError("سیاست ANY نقض شد: قواعد منطبق خروجی متفاوت دارند")
        return {**first, "_matchedRule": matched[0][0].get("id") or "rule-1"}

    if table.hit_policy == "PRIORITY":
        best = min(matched, key=lambda pair: int(pair[0].get("priority") or 10**9))
        return {**best[1], "_matchedRule": best[0].get("id") or "rule-1"}

    # FIRST — ترتیب فهرست
    rule, oe = matched[0]
    return {**oe, "_matchedRule": rule.get("id") or "rule-1"}


def _output_default(table: DecisionTable, name: str):
    for o in table.outputs:
        if o.get("name") == name:
            return o.get("defaultValue")
    return None


def evaluate_schema(schema: dict | None, data: dict) -> dict:
    """میانبر: ساخت جدول از schema و ارزیابی."""
    return evaluate_table(DecisionTable.from_schema(schema), data)
