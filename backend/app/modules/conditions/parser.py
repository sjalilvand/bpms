# -*- coding: utf-8 -*-
"""فاز ۴ — شرط‌ساز بصری روی نمودار BPMN.

پارسر امن مبتنی بر AST پایتون برای عبارت شرط مسیر (conditionExpression):
- ساختار تجزیه‌شده JSON برای ویرایشگر بصری (round-trip کامل)
- رندر ساختار به عبارت پایتونی معادل (موتور SpiffWorkflow شرط را با معنای پایتونی ارزیابی می‌کند)
- ارزیابی امن بدون eval — پیمایش مستقیم AST با فهرست سفید گره‌ها
- استخراج متغیرهای ارجاع‌شده برای اعتبارسنجی انتشار (هشدار متغیر ناشناخته)
"""
from __future__ import annotations

import ast
from typing import Any

# عملگرهای مجاز — نگاشت AST به شناسه ساختار
CMP_OPS = {
    ast.Eq: "eq", ast.NotEq: "ne", ast.Gt: "gt", ast.GtE: "ge", ast.Lt: "lt", ast.LtE: "le",
    ast.In: "in", ast.NotIn: "not_in",
}

MAX_DEPTH = 4          # حداکثر تودرتویی گروه‌ها
MAX_ITEMS = 20         # حداکثر شرط در هر سطح


class ConditionError(Exception):
    """خطای تجزیه/رندر شرط — پیام فارسی و قابل نمایش به طراح."""


# ---------------- تجزیه عبارت → ساختار ----------------
def parse(expr: str) -> dict:
    """عبارت پایتونی شرط را به ساختار JSON ویرایشگر بصری تبدیل می‌کند."""
    if not expr or not expr.strip():
        raise ConditionError("شرط خالی است")
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise ConditionError(f"نحو شرط نامعتبر است: {e.msg} (ستون {e.offset})")
    node = tree.body
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return {"combinator": "and", "items": []} if node.value else {"combinator": "and", "items": []}
        raise ConditionError("شرط باید یک مقایسه یا ترکیب منطقی باشد")
    items, combinator = _parse_node(node, 1)
    return {"combinator": combinator, "items": items}


def _parse_node(node: ast.AST, depth: int) -> tuple[list, str]:
    if depth > MAX_DEPTH:
        raise ConditionError("تودرتویی شرط بیش از حد مجاز است (حداکثر ۴ سطح)")
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            comb = "and"
        elif isinstance(node.op, ast.Or):
            comb = "or"
        else:
            raise ConditionError("عملگر منطقی پشتیبانی نمی‌شود")
        if len(node.values) > MAX_ITEMS:
            raise ConditionError(f"حداکثر {MAX_ITEMS} شرط در هر سطح مجاز است")
        items = []
        for v in node.values:
            sub_items, sub_comb = _parse_node(v, depth + 1)
            if len(sub_items) == 1 and sub_items[0]["kind"] == "compare":
                items.append(sub_items[0])
            else:
                items.append({"kind": "group", "combinator": sub_comb, "items": sub_items})
        return items, comb
    return [_parse_compare(node)], "and"


def _name_of(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_of(node.value)
        if not base:
            raise ConditionError("مسیر ویژگی تودرتو پشتیبانی نمی‌شود")
        return f"{base}.{node.attr}"
    return ""


def _literal(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)) or (
            isinstance(node, ast.Constant) and node.value is None):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_literal(x) for x in node.elts]
    raise ConditionError("مقدار سمت راست باید مقدار ثابت (رشته/عدد/درست‌نادرست/فهرست) باشد")


def _parse_compare(node: ast.AST) -> dict:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        inner = node.operand
        if isinstance(inner, (ast.Compare, ast.BoolOp)):
            c = _parse_compare(inner) if isinstance(inner, ast.Compare) else None
            if c is None:
                raise ConditionError("نفی گروه داخل شرط ساده پشتیبانی نمی‌شود؛ گروه را ویرایش کنید")
            c["negate"] = not c.get("negate", False)
            return c
        name = _name_of(inner)
        if name:
            return {"kind": "compare", "field": name, "op": "empty", "value": None}
        raise ConditionError("ساختار نفی پشتیبانی نمی‌شود")
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ConditionError("زنجیره مقایسه (a < b < c) پشتیبانی نمی‌شود")
        op = type(node.ops[0])
        left, right = node.left, node.comparators[0]
        # الگوی empty/not_empty: مقایسه با None از هر طرف (== ، != ، is ، is not)
        right_none = isinstance(right, ast.Constant) and right.value is None
        left_none = isinstance(left, ast.Constant) and left.value is None
        if right_none and _name_of(left) and op in (ast.Eq, ast.Is):
            return {"kind": "compare", "field": _name_of(left), "op": "empty", "value": None}
        if right_none and _name_of(left) and op in (ast.NotEq, ast.IsNot):
            return {"kind": "compare", "field": _name_of(left), "op": "not_empty", "value": None}
        # الگوی contains: مقدار ثابت in نام فیلد
        if op is ast.In and isinstance(left, ast.Constant) and _name_of(right):
            return {"kind": "compare", "field": _name_of(right), "op": "contains", "value": _literal(left)}
        if op is ast.NotIn and isinstance(left, ast.Constant) and _name_of(right):
            c = {"kind": "compare", "field": _name_of(right), "op": "contains", "value": _literal(left)}
            c["negate"] = True
            return c
        op_id = CMP_OPS.get(op)
        if not op_id:
            raise ConditionError("این عملگر در شرط‌ساز بصری پشتیبانی نمی‌شود")
        if left_none and _name_of(right):
            # None == field → خالی بودن
            if op_id == "eq":
                return {"kind": "compare", "field": _name_of(right), "op": "empty", "value": None}
            if op_id == "ne":
                return {"kind": "compare", "field": _name_of(right), "op": "not_empty", "value": None}
        name = _name_of(left)
        if not name:
            raise ConditionError("سمت چپ شرط باید نام فیلد باشد")
        if op_id in ("in", "not_in"):
            value = _literal(right)
            if not isinstance(value, list):
                raise ConditionError("عملگر in به فهرست مقادیر نیاز دارد")
        else:
            value = _literal(right)
        return {"kind": "compare", "field": name, "op": op_id, "value": value}
    raise ConditionError("این ساختار در شرط‌ساز بصری پشتیبانی نمی‌شود (عبارت دستی است)")


# ---------------- رندر ساختار → عبارت پایتونی ----------------
def _fmt_value(v: Any) -> str:
    if v is None:
        return "None"
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"
    if isinstance(v, list):
        return "[" + ", ".join(_fmt_value(x) for x in v) + "]"
    raise ConditionError("نوع مقدار پشتیبانی نمی‌شود")


OP_SYMBOL = {"eq": "==", "ne": "!=", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}


def _render_compare(c: dict) -> str:
    field, op, value = str(c.get("field") or ""), c.get("op"), c.get("value")
    if not field:
        raise ConditionError("نام فیلد شرط خالی است")
    negate = bool(c.get("negate"))
    body = None
    if op == "empty":
        body = f"{field} is None"
    elif op == "not_empty":
        body = f"{field} is not None"
    elif op == "contains":
        body = f"{_fmt_value(value)} in {field}"
    elif op == "in":
        if not isinstance(value, list) or not value:
            raise ConditionError("عملگر in به فهرست مقادیر غیرخالی نیاز دارد")
        body = f"{field} in {_fmt_value(value)}"
    elif op == "not_in":
        if not isinstance(value, list) or not value:
            raise ConditionError("عملگر not_in به فهرست مقادیر غیرخالی نیاز دارد")
        body = f"{field} not in {_fmt_value(value)}"
    elif op in OP_SYMBOL:
        body = f"{field} {OP_SYMBOL[op]} {_fmt_value(value)}"
    else:
        raise ConditionError(f"عملگر «{op}» شناخته‌شده نیست")
    if negate:
        body = f"not ({body})"
    return body


def render(structure: dict) -> str:
    """ساختار ویرایشگر بصری را به عبارت پایتونی معادل تبدیل می‌کند."""
    if not isinstance(structure, dict):
        raise ConditionError("ساختار شرط نامعتبر است")
    return _render_level(structure, 1)


def _render_level(level: dict, depth: int) -> str:
    if depth > MAX_DEPTH:
        raise ConditionError("تودرتویی شرط بیش از حد مجاز است")
    items = level.get("items") or []
    comb = level.get("combinator") or "and"
    if comb not in ("and", "or"):
        raise ConditionError("ترکیب شرط باید and یا or باشد")
    if len(items) > MAX_ITEMS:
        raise ConditionError(f"حداکثر {MAX_ITEMS} شرط در هر سطح مجاز است")
    parts = []
    for it in items:
        if not isinstance(it, dict):
            raise ConditionError("مورد شرط نامعتبر است")
        if it.get("kind") == "group":
            sub = _render_level(it, depth + 1)
            parts.append(f"({sub})")
        elif it.get("kind") == "compare":
            parts.append(_render_compare(it))
        else:
            raise ConditionError("نوع شرط شناخته‌شده نیست")
    if not parts:
        return "True"
    return f" {comb} ".join(parts)


# ---------------- ارزیابی امن (بدون eval) ----------------
def _resolve(node: ast.AST, data: dict, depth: int = 0) -> Any:
    if depth > 8:
        raise ConditionError("عمق ارزیابی بیش از حد مجاز")
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_resolve(e, data, depth + 1) for e in node.elts]
    if isinstance(node, ast.Name):
        return (data or {}).get(node.id)
    if isinstance(node, ast.Attribute):
        base = _resolve(node.value, data, depth + 1)
        if isinstance(base, dict):
            return base.get(node.attr)
        return None
    if isinstance(node, ast.BoolOp):
        vals = [_resolve(v, data, depth + 1) for v in node.values]
        truth = [bool(v) for v in vals]
        return all(truth) if isinstance(node.op, ast.And) else any(truth)
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return not bool(_resolve(node.operand, data, depth + 1))
        if isinstance(node.op, ast.USub):
            v = _resolve(node.operand, data, depth + 1)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return -v
            raise ConditionError("منفی کردن این مقدار مجاز نیست")
        raise ConditionError("عملگر یکانی پشتیبانی نمی‌شود")
    if isinstance(node, ast.Compare):
        left = _resolve(node.left, data, depth + 1)
        if len(node.ops) != 1:
            raise ConditionError("زنجیره مقایسه پشتیبانی نمی‌شود")
        right = _resolve(node.comparators[0], data, depth + 1)
        return _apply_cmp(type(node.ops[0]), left, right)
    raise ConditionError("گره غیرمجاز در ارزیابی شرط")


def _apply_cmp(op: type, left: Any, right: Any) -> bool:
    try:
        if op is ast.Eq:
            return left == right
        if op is ast.NotEq:
            return left != right
        if op is ast.Gt:
            return left > right
        if op is ast.GtE:
            return left >= right
        if op is ast.Lt:
            return left < right
        if op is ast.LtE:
            return left <= right
        if op is ast.In:
            return left in right if right is not None else False
        if op is ast.NotIn:
            return left not in right if right is not None else True
        if op is ast.Is:
            return left is right
        if op is ast.IsNot:
            return left is not right
    except TypeError:
        raise ConditionError("مقایسه این مقادیر ممکن نیست (ناسازگاری نوع)")
    raise ConditionError("عملگر مقایسه پشتیبانی نمی‌شود")


def evaluate(expr: str, data: dict | None) -> bool:
    """ارزیابی امن عبارت شرط روی داده — تنها با فهرست سفید گره‌ها."""
    if not expr or not expr.strip():
        return False
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise ConditionError(f"نحو شرط نامعتبر است: {e.msg}")
    return bool(_resolve(tree.body, data or {}, 0))


# ---------------- ابزارهای اعتبارسنجی ----------------
def extract_variables(expr: str) -> list[str]:
    """نام متغیرهای ارجاع‌شده در شرط (برای هشدار متغیر ناشناخته در انتشار)."""
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError:
        return []
    names: set[str] = set()

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            # مسیر ریشه‌ای ثبت شود (order.total → order)
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                names.add(root.id)
            for ch in ast.iter_child_nodes(node):
                visit(ch)
        else:
            for ch in ast.iter_child_nodes(node):
                visit(ch)

    visit(tree.body)
    return sorted(names)


def validate_structure(structure: dict) -> list[str]:
    """اعتبارسنجی ساختار ویرایشگر بصری — فهرست خطاها (خالی = معتبر)."""
    errors: list[str] = []

    def walk(level: dict, path: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            errors.append(f"{path}: تودرتویی بیش از حد مجاز")
            return
        items = level.get("items")
        if not isinstance(items, list):
            errors.append(f"{path}: فهرست شرط‌ها نامعتبر است")
            return
        if not items:
            errors.append(f"{path}: حداقل یک شرط لازم است")
            return
        if len(items) > MAX_ITEMS:
            errors.append(f"{path}: حداکثر {MAX_ITEMS} شرط مجاز است")
        for i, it in enumerate(items):
            p = f"{path}[{i + 1}]"
            if not isinstance(it, dict):
                errors.append(f"{p}: مورد نامعتبر")
                continue
            if it.get("kind") == "group":
                walk(it, p, depth + 1)
            elif it.get("kind") == "compare":
                if not str(it.get("field") or "").strip():
                    errors.append(f"{p}: نام فیلد خالی است")
                op = it.get("op")
                if op in ("in", "not_in") and not isinstance(it.get("value"), list):
                    errors.append(f"{p}: عملگر in به فهرست مقادیر نیاز دارد")
                if op == "contains" and it.get("value") is None:
                    errors.append(f"{p}: مقدار عملگر contains خالی است")
                if op not in list(OP_SYMBOL) + ["in", "not_in", "contains", "empty", "not_empty"]:
                    errors.append(f"{p}: عملگر «{op}» مجاز نیست")
            else:
                errors.append(f"{p}: نوع شرط نامعتبر")

    walk(structure, "شرط", 1)
    return errors
