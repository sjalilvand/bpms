# -*- coding: utf-8 -*-
"""تست موتور جدول تصمیم (DMN سبک فاز ۳) — سیاست‌های برخورد، عملگرها، اعتبارسنجی."""
import pytest

from app.modules.decisions.engine import (
    DecisionTable, DecisionError, evaluate_table, evaluate_schema,
)
from app.modules.decisions.service import validate_version_schema


SCHEMA_FIRST = {
    "hitPolicy": "FIRST",
    "inputs": [{"name": "amount", "label": "مبلغ", "type": "number"},
               {"name": "kind", "label": "نوع", "type": "string"}],
    "outputs": [{"name": "level", "label": "سطح", "defaultValue": "low"}],
    "rules": [
        {"id": "r1", "inputEntries": {"amount": "> 100", "kind": "-"},
         "outputEntries": {"level": "high"}, "priority": 1, "enabled": True},
        {"id": "r2", "inputEntries": {"amount": "between 50..100", "kind": "in a,b"},
         "outputEntries": {"level": "mid"}, "priority": 2, "enabled": True},
        {"id": "r3", "inputEntries": {"amount": "<= 50", "kind": "-"},
         "outputEntries": {"level": "low"}, "priority": 3, "enabled": True},
    ],
}


class TestEntryMatching:
    def test_operators(self):
        schema = dict(SCHEMA_FIRST)
        assert evaluate_schema(schema, {"amount": 150, "kind": "x"})["level"] == "high"
        assert evaluate_schema(schema, {"amount": 75, "kind": "a"})["level"] == "mid"
        assert evaluate_schema(schema, {"amount": 75, "kind": "c"})["level"] == "low"
        assert evaluate_schema(schema, {"amount": 10, "kind": "x"})["level"] == "low"

    def test_wildcard_dash(self):
        schema = dict(SCHEMA_FIRST)
        out = evaluate_schema(schema, {"amount": 200, "kind": "zzz"})
        assert out["_matchedRule"] == "r1"

    def test_string_equality(self):
        schema = {"hitPolicy": "FIRST",
                  "inputs": [{"name": "status", "type": "string"}],
                  "outputs": [{"name": "ok", "defaultValue": False}],
                  "rules": [{"id": "r", "inputEntries": {"status": "== 'done'"},
                             "outputEntries": {"ok": True}}]}
        assert evaluate_schema(schema, {"status": "done"})["ok"] is True
        assert evaluate_schema(schema, {"status": "new"})["ok"] is False

    def test_not_equal(self):
        schema = {"hitPolicy": "FIRST",
                  "inputs": [{"name": "x", "type": "number"}],
                  "outputs": [{"name": "y", "defaultValue": 0}],
                  "rules": [{"id": "r", "inputEntries": {"x": "!= 5"}, "outputEntries": {"y": 1}}]}
        assert evaluate_schema(schema, {"x": 3})["y"] == 1
        assert evaluate_schema(schema, {"x": 5})["y"] == 0

    def test_boolean_and_membership(self):
        schema = {"hitPolicy": "FIRST",
                  "inputs": [{"name": "flag", "type": "boolean"}],
                  "outputs": [{"name": "o", "defaultValue": 0}],
                  "rules": [{"id": "r", "inputEntries": {"flag": "true"}, "outputEntries": {"o": 1}}]}
        assert evaluate_schema(schema, {"flag": True})["o"] == 1
        assert evaluate_schema(schema, {"flag": False})["o"] == 0

    def test_combined_or_expression(self):
        schema = {"hitPolicy": "FIRST",
                  "inputs": [{"name": "n", "type": "number"}],
                  "outputs": [{"name": "o", "defaultValue": 0}],
                  "rules": [{"id": "r", "inputEntries": {"n": "< 0 || > 10"}, "outputEntries": {"o": 1}}]}
        assert evaluate_schema(schema, {"n": 15})["o"] == 1
        assert evaluate_schema(schema, {"n": 5})["o"] == 0
        assert evaluate_schema(schema, {"n": -2})["o"] == 1

    def test_missing_input_raises(self):
        with pytest.raises(DecisionError):
            evaluate_schema(SCHEMA_FIRST, {"amount": 10})


class TestHitPolicies:
    def test_collect_returns_all_matches(self):
        schema = {"hitPolicy": "COLLECT",
                  "inputs": [{"name": "n", "type": "number"}],
                  "outputs": [{"name": "tag", "defaultValue": None}],
                  "rules": [
                      {"id": "a", "inputEntries": {"n": "> 5"}, "outputEntries": {"tag": "A"}},
                      {"id": "b", "inputEntries": {"n": "> 8"}, "outputEntries": {"tag": "B"}},
                      {"id": "c", "inputEntries": {"n": "< 3"}, "outputEntries": {"tag": "C"}},
                  ]}
        out = evaluate_schema(schema, {"n": 10})
        assert out["matched"] == 2
        assert {"tag": "A"} in out["results"]
        assert {"tag": "B"} in out["results"]

    def test_unique_conflict_raises(self):
        schema = {"hitPolicy": "UNIQUE",
                  "inputs": [{"name": "n", "type": "number"}],
                  "outputs": [{"name": "o", "defaultValue": None}],
                  "rules": [
                      {"id": "a", "inputEntries": {"n": "> 5"}, "outputEntries": {"o": 1}},
                      {"id": "b", "inputEntries": {"n": "> 8"}, "outputEntries": {"o": 2}},
                  ]}
        with pytest.raises(DecisionError):
            evaluate_schema(schema, {"n": 10})
        assert evaluate_schema(schema, {"n": 6})["o"] == 1

    def test_any_conflict_raises(self):
        schema = {"hitPolicy": "ANY",
                  "inputs": [{"name": "n", "type": "number"}],
                  "outputs": [{"name": "o", "defaultValue": None}],
                  "rules": [
                      {"id": "a", "inputEntries": {"n": "> 5"}, "outputEntries": {"o": 1}},
                      {"id": "b", "inputEntries": {"n": "> 8"}, "outputEntries": {"o": 2}},
                  ]}
        with pytest.raises(DecisionError):
            evaluate_schema(schema, {"n": 10})

    def test_any_same_outputs_ok(self):
        schema = {"hitPolicy": "ANY",
                  "inputs": [{"name": "n", "type": "number"}],
                  "outputs": [{"name": "o", "defaultValue": None}],
                  "rules": [
                      {"id": "a", "inputEntries": {"n": "> 5"}, "outputEntries": {"o": 1}},
                      {"id": "b", "inputEntries": {"n": "> 8"}, "outputEntries": {"o": 1}},
                  ]}
        assert evaluate_schema(schema, {"n": 10})["o"] == 1

    def test_priority_picks_lowest_number(self):
        schema = {"hitPolicy": "PRIORITY",
                  "inputs": [{"name": "n", "type": "number"}],
                  "outputs": [{"name": "o", "defaultValue": None}],
                  "rules": [
                      {"id": "a", "inputEntries": {"n": "> 5"}, "outputEntries": {"o": "urgent"}, "priority": 5},
                      {"id": "b", "inputEntries": {"n": "> 8"}, "outputEntries": {"o": "critical"}, "priority": 2},
                  ]}
        assert evaluate_schema(schema, {"n": 10})["o"] == "critical"
        assert evaluate_schema(schema, {"n": 6})["o"] == "urgent"

    def test_first_keeps_order(self):
        schema = dict(SCHEMA_FIRST)
        assert evaluate_schema(schema, {"amount": 90, "kind": "a"})["_matchedRule"] == "r2"
        assert evaluate_schema(schema, {"amount": 200, "kind": "b"})["_matchedRule"] == "r1"

    def test_no_match_uses_defaults(self):
        schema = {"hitPolicy": "FIRST",
                  "inputs": [{"name": "n", "type": "number"}],
                  "outputs": [{"name": "o", "defaultValue": "fallback"}],
                  "rules": [{"id": "r", "inputEntries": {"n": "> 100"}, "outputEntries": {"o": "x"}}]}
        out = evaluate_schema(schema, {"n": 5})
        assert out["o"] == "fallback"
        assert out["_matchedRule"] is None


class TestValidation:
    def test_valid_schema_has_no_errors(self):
        assert validate_version_schema(SCHEMA_FIRST) == []

    def test_empty_rules_rejected(self):
        schema = {"hitPolicy": "FIRST", "inputs": [{"name": "n"}],
                  "outputs": [{"name": "o"}], "rules": []}
        errors = validate_version_schema(schema)
        assert any("قاعده" in e for e in errors)

    def test_unknown_output_name_rejected(self):
        schema = {"hitPolicy": "FIRST", "inputs": [{"name": "n"}],
                  "outputs": [{"name": "o"}],
                  "rules": [{"id": "r", "inputEntries": {"n": "> 1"}, "outputEntries": {"oops": 1}}]}
        errors = validate_version_schema(schema)
        assert any("خروجی ناشناس" in e for e in errors)

    def test_bad_expression_rejected(self):
        schema = {"hitPolicy": "FIRST", "inputs": [{"name": "n"}],
                  "outputs": [{"name": "o"}],
                  "rules": [{"id": "r", "inputEntries": {"n": "between 5"}, "outputEntries": {"o": 1}}]}
        errors = validate_version_schema(schema)
        assert any("بازه" in e for e in errors)

    def test_unsupported_hit_policy(self):
        with pytest.raises(DecisionError):
            DecisionTable.from_schema({"hitPolicy": "XOR", "inputs": [], "outputs": [], "rules": []})

    def test_disabled_rule_is_ignored(self):
        schema = {"hitPolicy": "FIRST",
                  "inputs": [{"name": "n", "type": "number"}],
                  "outputs": [{"name": "o", "defaultValue": 0}],
                  "rules": [
                      {"id": "off", "inputEntries": {"n": "> 1"}, "outputEntries": {"o": 9}, "enabled": False},
                      {"id": "on", "inputEntries": {"n": "> 1"}, "outputEntries": {"o": 1}, "enabled": True},
                  ]}
        assert evaluate_schema(schema, {"n": 5})["o"] == 1
