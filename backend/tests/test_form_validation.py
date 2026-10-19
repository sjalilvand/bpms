# -*- coding: utf-8 -*-
"""تست‌های موتور اعتبارسنجی فرم و فرمول امن (سند §۱۳ و AC-08)."""
import pytest

from app.core.database import SessionLocal
from app.modules.forms.safeeval import evaluate_formula, evaluate_condition, FormulaError
from app.modules.forms.validator import validate_form_data


@pytest.fixture()
def db():
    db = SessionLocal()
    yield db
    db.close()


class TestSafeEval:
    def test_arithmetic(self):
        assert evaluate_formula("2 + 3 * 4", lambda k: 0) == 14

    def test_field_reference(self):
        assert evaluate_formula("qty * price", lambda k: {"qty": 3, "price": 15000}.get(k)) == 45000

    def test_sum_over_subform(self):
        rows = [{"row_total": 1000}, {"row_total": 2500}, {"row_total": 500}]
        assert evaluate_formula("SUM(items.row_total)", lambda k: rows if k.startswith("__list__items") else None) == 4000

    def test_condition(self):
        assert evaluate_condition("total > 10000000", lambda k: {"total": 15000000}.get(k)) is True
        assert evaluate_condition("action == 'approve'", lambda k: {"action": "approve"}.get(k)) is True
        assert evaluate_condition("action == 'approve'", lambda k: {"action": "reject"}.get(k)) is False

    def test_no_eval_of_code(self):
        # اجرای کد آزاد مجاز نیست — باید None (خطا) برگردد
        assert evaluate_formula("__import__('os').system('id')", lambda k: None) is None
        assert evaluate_formula("open('/etc/passwd')", lambda k: None) is None

    def test_if_and_round(self):
        assert evaluate_formula("IF(total > 100, 'بالا', 'پایین')", lambda k: {"total": 150}.get(k)) == "بالا"
        assert evaluate_formula("ROUND(10 / 3, 2)", lambda k: None) == 3.33

    def test_division_by_zero_safe(self):
        assert evaluate_formula("10 / 0", lambda k: None) is None


class TestFormValidation:
    SCHEMA = {
        "fields": [
            {"key": "name", "type": "text", "label": "نام", "required": True, "maxLength": 10},
            {"key": "nid", "type": "national_id", "label": "کد ملی", "required": True},
            {"key": "mobile", "type": "mobile", "label": "موبایل"},
            {"key": "amount", "type": "money", "label": "مبلغ", "min": 0},
            {"key": "total", "type": "calculated", "formula": "SUM(items.row_total)"},
            {"key": "items", "type": "subform", "label": "اقلام", "minRows": 1, "maxRows": 3,
             "subformId": 999},
        ]
    }
    SUB_SCHEMA = {
        "fields": [
            {"key": "row_total", "type": "calculated", "formula": "qty * price"},
            {"key": "qty", "type": "integer", "label": "تعداد", "min": 1},
            {"key": "price", "type": "money", "label": "قیمت"},
        ]
    }

    class _FakeDB:
        """واکشی زیرفرم بدون دیتابیس واقعی."""

        def fake(self):
            pass

    def _validate(self, data, partial=False):
        from app.modules.forms import validator as V
        orig = V._load_subform_schema
        V._load_subform_schema = lambda db, fid: self.SUB_SCHEMA
        try:
            return validate_form_data(None, self.SCHEMA, data, partial=partial)
        finally:
            V._load_subform_schema = orig

    def test_required_errors(self):
        r = self._validate({})
        keys = {e["key"] for e in r.errors}
        assert "name" in keys and "nid" in keys

    def test_national_id_invalid(self):
        r = self._validate({"name": "علی", "nid": "1111111111"})
        assert any(e["key"] == "nid" for e in r.errors)

    def test_national_id_normalized_and_valid(self):
        r = self._validate({"name": "علی", "nid": "۰۶۸۴۱۵۹۴۱۴", "mobile": "۰۹۱۲۳۴۵۶۷۸۹", "items": [{"qty": 1, "price": 1000}]})
        assert r.ok, r.errors
        assert r.cleaned["nid"] == "0684159414"
        assert r.cleaned["mobile"] == "09123456789"

    def test_subform_rows_and_total(self):
        r = self._validate({
            "name": "علی", "nid": "0684159414",
            "items": [{"qty": 2, "price": 10000}, {"qty": 1, "price": 5000}],
        })
        assert r.ok, r.errors
        assert r.cleaned["items"][0]["row_total"] == 20000
        assert r.cleaned["total"] == 25000

    def test_subform_min_rows(self):
        r = self._validate({"name": "علی", "nid": "0684159414", "items": []})
        assert any("حداقل" in e["message"] for e in r.errors)

    def test_subform_row_validation(self):
        r = self._validate({"name": "علی", "nid": "0684159414", "items": [{"qty": 0, "price": 100}]})
        assert any(e["key"].startswith("items[0].qty") for e in r.errors)

    def test_partial_skips_required(self):
        r = self._validate({}, partial=True)
        assert r.ok

    def test_text_max_length(self):
        r = self._validate({"name": "نام بلندتر از ده نویسه", "nid": "0684159414"})
        assert any(e["key"] == "name" for e in r.errors)
