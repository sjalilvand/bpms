# -*- coding: utf-8 -*-
"""ارزیاب عبارات محدود و نوع‌دار برای فرمول‌ها و شروط — بدون eval/exec.

عملگرها: + - * / % ( ) > < >= <= == != && || !
توابع مجاز: SUM(field)، MIN(field)، MAX(field)، COUNT(field)، ROUND(x, n)، ABS(x)، IF(c,a,b)
شناسه‌ها به مقادیر فیلدها اشاره می‌کنند.
این ارزیاب برای فرم‌ساز طراحی شده و جایگزین اجرای آزاد کد کاربران است (قاعده امنیتی سند).
"""
from __future__ import annotations

import re
from typing import Any, Callable

TOKEN_RE = re.compile(r"""
    \s*(?:
    (?P<num>\d+\.\d+|\d+)|
    (?P<str>'[^']*'|"[^"]*")|
    (?P<op><=|>=|==|!=|&&|\|\||[+\-*/%()<>!,.])|
    (?P<ident>[A-Za-z_\u0600-\u06FF][A-Za-z0-9_\u0600-\u06FF]*)
    )""", re.VERBOSE)

KEYWORDS = {"SUM", "MIN", "MAX", "COUNT", "ROUND", "ABS", "IF", "true", "false", "True", "False", "and", "or", "not"}


class FormulaError(Exception):
    pass


def tokenize(expr: str) -> list[tuple[str, str]]:
    tokens, pos = [], 0
    while pos < len(expr):
        m = TOKEN_RE.match(expr, pos)
        if not m:
            if expr[pos:].strip() == "":
                break
            raise FormulaError(f"نویسه نامعتبر در عبارت: {expr[pos:pos+5]!r}")
        pos = m.end()
        for kind in ("num", "str", "op", "ident"):
            if m.group(kind) is not None:
                tokens.append((kind, m.group(kind)))
                break
    return tokens


class Parser:
    """Parser بازگشتی-نزولی برای عبارات منطقی/محاسباتی."""

    def __init__(self, tokens, resolver: Callable[[str], Any]):
        self.toks = tokens
        self.i = 0
        self.resolver = resolver

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def next(self):
        t = self.peek()
        self.i += 1
        return t

    def expect(self, val):
        k, v = self.next()
        if v != val:
            raise FormulaError(f"انتظار «{val}» اما «{v}» دیده شد")

    # or_expr -> and_expr (|| and_expr)*
    def parse_or(self):
        left = self.parse_and()
        while self.peek()[1] == "||" or self.peek() == ("ident", "or"):
            self.next()
            right = self.parse_and()
            left = (left or right) if isinstance(left, bool) or isinstance(right, bool) else bool(left or right)
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.peek()[1] == "&&" or self.peek() == ("ident", "and"):
            self.next()
            right = self.parse_not()
            left = bool(left and right)
        return left

    def parse_not(self):
        if self.peek()[1] == "!" or self.peek() == ("ident", "not"):
            self.next()
            return not bool(self.parse_not())
        return self.parse_cmp()

    def parse_cmp(self):
        left = self.parse_add()
        op = self.peek()[1]
        if op in ("<", ">", "<=", ">=", "==", "!="):
            self.next()
            right = self.parse_add()
            if op == "<":
                return left < right
            if op == ">":
                return left > right
            if op == "<=":
                return left <= right
            if op == ">=":
                return left >= right
            if op == "==":
                return left == right
            return left != right
        return left

    def parse_add(self):
        left = self.parse_mul()
        while self.peek()[1] in ("+", "-"):
            op = self.next()[1]
            right = self.parse_mul()
            if op == "+":
                # الحاق رشته فقط اگر هر دو رشته باشند؛ وگرنه جمع عددی
                if isinstance(left, str) and isinstance(right, str):
                    left = left + right
                else:
                    left = _num(left) + _num(right)
            else:
                left = _num(left) - _num(right)
        return left

    def parse_mul(self):
        left = self.parse_unary()
        while self.peek()[1] in ("*", "/", "%"):
            op = self.next()[1]
            right = self.parse_unary()
            if op == "*":
                left = _num(left) * _num(right)
            elif op == "/":
                d = _num(right)
                if d == 0:
                    raise FormulaError("تقسیم بر صفر")
                left = _num(left) / d
            else:
                d = _num(right)
                if d == 0:
                    raise FormulaError("باقیمانده بر صفر")
                left = _num(left) % d
        return left

    def parse_unary(self):
        k, v = self.peek()
        if v == "-":
            self.next()
            return -_num(self.parse_unary())
        if v == "+":
            self.next()
            return _num(self.parse_unary())
        return self.parse_primary()

    def parse_primary(self):
        kind, val = self.next()
        if kind == "num":
            return float(val) if "." in val else int(val)
        if kind == "str":
            return val[1:-1]
        if kind == "ident":
            low = val.lower()
            if low in ("true",):
                return True
            if low in ("false",):
                return False
            if val.upper() in ("SUM", "MIN", "MAX", "COUNT", "ROUND", "ABS", "IF"):
                return self.parse_call(val.upper())
            return self.resolver(val)
        if val == "(":
            inner = self.parse_or()
            self.expect(")")
            return inner
        raise FormulaError(f"عبارت نامعتبر نزدیک «{val}»")

    def parse_call(self, fn):
        self.expect("(")
        args = []
        if fn in ("SUM", "MIN", "MAX", "COUNT"):
            # مسیر تجمیعی: items.qty یا items — به‌جای عبارت کامل
            path = self.parse_path()
            self.expect(")")
            return self.aggregate(fn, path)
        if self.peek()[1] != ")":
            args.append(self.parse_or())
            while self.peek()[1] == ",":
                self.next()
                args.append(self.parse_or())
        self.expect(")")
        return self.call(fn, args)

    def parse_path(self) -> str:
        k, v = self.next()
        if k != "ident":
            raise FormulaError("نام فیلد آرایه‌ای لازم است")
        path = v
        while self.peek()[1] == ".":
            self.next()
            k2, v2 = self.next()
            if k2 != "ident":
                raise FormulaError("مسیر فیلد نامعتبر است")
            path += "." + v2
        return path

    def aggregate(self, fn, path: str):
        parts = path.split(".")
        rows = self.resolver(f"__list__{parts[0]}")
        if rows is None:
            rows = []
        if len(parts) == 1:
            values = [v for v in rows if v is not None and v != ""]
        else:
            leaf = parts[-1]
            values = []
            for row in rows:
                if isinstance(row, dict):
                    values.append(row.get(leaf))
                else:
                    values.append(None)
        nums = [_num(v) for v in values if v is not None and v != ""]
        if fn == "COUNT":
            return len(values) if len(parts) == 1 else len(nums)
        if fn == "SUM":
            return sum(nums)
        if not nums:
            return 0
        return min(nums) if fn == "MIN" else max(nums)

    def call(self, fn, args):
        if fn == "ROUND":
            if len(args) == 1:
                return round(_num(args[0]), 0)
            return round(_num(args[0]), int(_num(args[1])))
        if fn == "ABS":
            return abs(_num(args[0]))
        if fn == "IF":
            if len(args) != 3:
                raise FormulaError("IF سه آرگومان می‌گیرد")
            return args[1] if args[0] else args[2]
        raise FormulaError(f"تابع «{fn}» مجاز نیست")


def _num(v) -> float:
    if v is None or v == "":
        return 0
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    try:
        s = str(v).strip().replace(",", "")
        return float(s) if "." in s else int(s)
    except (ValueError, TypeError):
        raise FormulaError(f"«{v}» عدد نیست")


def evaluate_formula(expr: str, resolver: Callable[[str], Any], default=None):
    """ارزیابی عبارت؛ در صورت خطا default (یا None) برمی‌گردد.

    resolver(key) مقدار فیلد را برمی‌گرداند؛ برای SUM ... کلید با پیشوند __list__ پاس می‌شود.
    """
    if not expr or not expr.strip():
        return default
    try:
        p = Parser(tokenize(expr), resolver)
        result = p.parse_or()
        if p.peek()[0] is not None:
            raise FormulaError("عبارت کامل تجزیه نشد")
        return result
    except FormulaError:
        return default
    except (TypeError, ValueError):
        return default


def evaluate_condition(expr: str, resolver) -> bool:
    """ارزیابی شرط؛ خطا = نادرست (safe-fail)."""
    return bool(evaluate_formula(expr, resolver, default=False))
