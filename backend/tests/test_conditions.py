# -*- coding: utf-8 -*-
"""آزمون‌های فاز ۴ — پارسر، رندر و ارزیابی امن شرط مسیر (شرط‌ساز بصری)."""
import pytest

from app.modules.conditions import parser
from app.modules.conditions.parser import ConditionError


# ---------------- تجزیه عبارت → ساختار ----------------
def test_parse_simple_equality():
    s = parser.parse("action == 'approve'")
    assert s["combinator"] == "and"
    assert s["items"] == [{"kind": "compare", "field": "action", "op": "eq", "value": "approve"}]


def test_parse_and_combination():
    s = parser.parse("total_amount >= 1000000 and priority == 'high'")
    assert s["combinator"] == "and"
    assert len(s["items"]) == 2
    assert s["items"][0] == {"kind": "compare", "field": "total_amount", "op": "ge", "value": 1000000}
    assert s["items"][1]["field"] == "priority"


def test_parse_or_combination():
    s = parser.parse("priority == 'high' or priority == 'normal'")
    assert s["combinator"] == "or"
    assert len(s["items"]) == 2


def test_parse_nested_group():
    s = parser.parse("total_amount > 100 and (unit == 'IT' or unit == 'FIN')")
    assert s["combinator"] == "and"
    group = s["items"][1]
    assert group["kind"] == "group"
    assert group["combinator"] == "or"
    assert group["items"][0]["field"] == "unit"


def test_parse_in_operator():
    s = parser.parse("status in ['new', 'open']")
    assert s["items"][0] == {"kind": "compare", "field": "status", "op": "in", "value": ["new", "open"]}


def test_parse_not_in_operator():
    s = parser.parse("status not in ['closed']")
    it = s["items"][0]
    assert it["op"] == "not_in" or (it.get("op") == "in" and it.get("negate"))
    assert it["value"] == ["closed"]


def test_parse_contains_pattern():
    # الگوی «مقدار in فیلد» → contains
    s = parser.parse("'urgent' in tags")
    assert s["items"][0] == {"kind": "compare", "field": "tags", "op": "contains", "value": "urgent"}


def test_parse_empty_and_not_empty():
    s = parser.parse("reviewer is None")
    assert s["items"][0]["op"] == "empty"
    s2 = parser.parse("reviewer is not None")
    assert s2["items"][0]["op"] == "not_empty"


def test_parse_negate_not():
    s = parser.parse("not (approved == True)")
    it = s["items"][0]
    assert it["field"] == "approved" and it.get("negate") is True


def test_parse_boolean_and_none_literals():
    s = parser.parse("needs_review == True and manager_id != None")
    assert s["items"][0]["value"] is True
    assert s["items"][1]["op"] == "not_empty"


def test_parse_dotted_path():
    s = parser.parse("order.total > 1000")
    assert s["items"][0]["field"] == "order.total"


def test_parse_syntax_error():
    with pytest.raises(ConditionError):
        parser.parse("action ==")


def test_parse_rejects_call():
    with pytest.raises(ConditionError):
        parser.parse("__import__('os').system('x')")


def test_parse_rejects_chained_compare():
    with pytest.raises(ConditionError):
        parser.parse("1 < total < 100")


def test_parse_rejects_deep_nesting():
    expr = "(((((a == 1)))))"
    s = parser.parse(expr)  # پرانتز تودرتو بدون گروه منطقی مجاز است
    assert s["items"][0]["field"] == "a"


# ---------------- رندر ساختار → عبارت ----------------
def test_render_roundtrip_simple():
    struct = {"combinator": "and", "items": [
        {"kind": "compare", "field": "action", "op": "eq", "value": "approve"}]}
    assert parser.render(struct) == "action == 'approve'"


def test_render_roundtrip_and_or():
    struct = {"combinator": "and", "items": [
        {"kind": "compare", "field": "total_amount", "op": "ge", "value": 1000000},
        {"kind": "group", "combinator": "or", "items": [
            {"kind": "compare", "field": "priority", "op": "eq", "value": "high"},
            {"kind": "compare", "field": "priority", "op": "eq", "value": "normal"},
        ]},
    ]}
    expr = parser.render(struct)
    assert expr == "total_amount >= 1000000 and (priority == 'high' or priority == 'normal')"
    # round-trip کامل: رندر → تجزیه → رندر باید ثابت بماند
    assert parser.render(parser.parse(expr)) == expr


def test_render_in_contains_empty():
    struct = {"combinator": "and", "items": [
        {"kind": "compare", "field": "status", "op": "in", "value": ["new", "open"]},
        {"kind": "compare", "field": "tags", "op": "contains", "value": "urgent"},
        {"kind": "compare", "field": "reviewer", "op": "empty"},
    ]}
    expr = parser.render(struct)
    assert "status in ['new', 'open']" in expr
    assert "'urgent' in tags" in expr
    assert "reviewer is None" in expr
    # round-trip
    assert parser.render(parser.parse(expr)) == expr


def test_render_escape_string():
    struct = {"combinator": "and", "items": [
        {"kind": "compare", "field": "note", "op": "eq", "value": "it's ok"}]}
    expr = parser.render(struct)
    assert expr == r"note == 'it\'s ok'"
    # بازخوانی مجدد همان مقدار
    assert parser.parse(expr)["items"][0]["value"] == "it's ok"


def test_render_empty_items_true():
    assert parser.render({"combinator": "and", "items": []}) == "True"


def test_render_rejects_empty_field():
    with pytest.raises(ConditionError):
        parser.render({"combinator": "and", "items": [{"kind": "compare", "field": "", "op": "eq", "value": 1}]})


# ---------------- ارزیابی امن ----------------
def test_evaluate_simple_true_false():
    data = {"action": "approve", "total_amount": 25000000}
    assert parser.evaluate("action == 'approve'", data) is True
    assert parser.evaluate("action == 'reject'", data) is False
    assert parser.evaluate("total_amount > 10000000", data) is True


def test_evaluate_combined():
    data = {"total_amount": 25000000, "priority": "high"}
    assert parser.evaluate("total_amount >= 10000000 and priority == 'high'", data) is True
    assert parser.evaluate("total_amount >= 50000000 or priority == 'low'", data) is False


def test_evaluate_in_contains():
    data = {"status": "open", "tags": ["urgent", "it"]}
    assert parser.evaluate("status in ['open', 'new']", data) is True
    assert parser.evaluate("'urgent' in tags", data) is True
    assert parser.evaluate("'finance' in tags", data) is False


def test_evaluate_missing_var_is_none():
    data = {"x": 1}
    assert parser.evaluate("missing is None", data) is True
    assert parser.evaluate("missing == 'x'", data) is False


def test_evaluate_dotted_path():
    data = {"order": {"total": 5000}}
    assert parser.evaluate("order.total > 1000", data) is True
    assert parser.evaluate("order.total > 9000", data) is False


def test_evaluate_rejects_dangerous_ast():
    # حتی اگر عبارت از مسیر دیگری تزریق شود، ارزیاب فقط گره‌های سفید را اجرا می‌کند
    with pytest.raises(ConditionError):
        parser.evaluate("__import__('os')", {})


def test_evaluate_empty_expr_false():
    assert parser.evaluate("", {}) is False
    assert parser.evaluate("   ", {}) is False


# ---------------- اعتبارسنجی ساختار و متغیرها ----------------
def test_validate_structure_errors():
    errs = parser.validate_structure({"combinator": "and", "items": []})
    assert any("حداقل یک شرط" in e for e in errs)
    errs2 = parser.validate_structure({"combinator": "and", "items": [
        {"kind": "compare", "field": "  ", "op": "eq", "value": 1}]})
    assert any("نام فیلد خالی" in e for e in errs2)


def test_validate_structure_ok():
    assert parser.validate_structure({"combinator": "and", "items": [
        {"kind": "compare", "field": "a", "op": "eq", "value": 1}]}) == []


def test_extract_variables():
    vars_ = parser.extract_variables("total_amount > 100 and order.unit == 'IT' or _initiator_id == 5")
    assert "total_amount" in vars_ and "order" in vars_ and "_initiator_id" in vars_


def test_extract_variables_invalid_expr():
    assert parser.extract_variables("action ==") == []


# ---------------- سازگاری با BPMN نمونه ----------------
def test_parse_purchase_bpmn_conditions():
    from app.modules.engine import adapter
    with open("data/bpmn/purchase_request.bpmn", encoding="utf-8") as fh:
        xml = fh.read()
    import re
    conds = re.findall(r"<bpmn:conditionExpression[^>]*>([^<]+)</bpmn:conditionExpression>", xml)
    assert len(conds) >= 2
    for c in conds:
        struct = parser.parse(c)
        assert parser.render(parser.parse(parser.render(struct))) == parser.render(struct)
        assert parser.evaluate(parser.render(struct), {"action": "approve"}) in (True, False)
