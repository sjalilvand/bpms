# -*- coding: utf-8 -*-
"""تست‌های واحد اعتبارسنجی ایرانی (سند §۱۴ و AC-04/05/06)."""
import pytest

from app.modules.forms.persian import (
    normalize_digits, is_valid_national_id, is_valid_mobile, normalize_mobile,
    jalali_to_gregorian_str, gregorian_to_jalali_str, is_valid_jalali_date,
)


class TestDigits:
    def test_persian_to_english(self):
        assert normalize_digits("۰۱۲۳۴۵۶۷۸۹") == "0123456789"

    def test_arabic_to_english(self):
        assert normalize_digits("٠١٢٣٤٥٦٧٨٩") == "0123456789"

    def test_trim(self):
        assert normalize_digits("  ۰۹۱۲  ") == "0912"

    def test_leading_zero_preserved(self):
        # صفر ابتدایی حفظ شود (کد ملی/موبایل رشته ذخیره می‌شوند)
        assert normalize_digits("۰۰۴۹۹۱۲۳۴۵") == "0049912345"


class TestNationalId:
    def test_valid_checksum(self):
        # کد ملی معتبر از نظر الگوریتم
        assert is_valid_national_id("0684159414") is True
        assert is_valid_national_id("1234567891") is True

    def test_persian_digits_accepted(self):
        assert is_valid_national_id("۰۶۸۴۱۵۹۴۱۴") is True

    def test_invalid_checksum(self):
        assert is_valid_national_id("0684159415") is False

    def test_same_digits_rejected(self):
        assert is_valid_national_id("1111111111") is False
        assert is_valid_national_id("0000000000") is False

    def test_wrong_length(self):
        assert is_valid_national_id("12345") is False
        assert is_valid_national_id("12345678901") is False

    def test_leading_zero_preserved_as_string(self):
        from app.modules.forms.persian import normalize_national_id
        assert normalize_national_id("۰۶۸۴۱۵۹۴۱۴") == "0684159414"


class TestMobile:
    def test_valid(self):
        assert is_valid_mobile("09123456789") is True

    def test_persian_digits(self):
        assert is_valid_mobile("۰۹۱۲۳۴۵۶۷۸۹") is True

    def test_plus98_normalized(self):
        assert normalize_mobile("+989123456789") == "09123456789"
        assert is_valid_mobile("+989123456789") is True

    def test_0098_normalized(self):
        assert is_valid_mobile("00989123456789") is True

    def test_invalid(self):
        assert is_valid_mobile("0912345678") is False      # 10 رقم
        assert is_valid_mobile("08123456789") is False     # پیش‌شماره غلط
        assert is_valid_mobile("091234567890") is False    # 12 رقم


class TestJalali:
    def test_valid_date(self):
        assert jalali_to_gregorian_str("1403/05/02") == "2024-07-23"

    def test_persian_digits(self):
        assert jalali_to_gregorian_str("۱۴۰۳/۰۵/۰۲") == "2024-07-23"

    def test_invalid_day(self):
        assert jalali_to_gregorian_str("1403/12/31") is None  # اسفند غیرکبیسه ۳۱ روز ندارد

    def test_leap_year_esfand_30(self):
        # ۱۴۰۳ کبیسه است
        assert is_valid_jalali_date(1403, 12, 30) is True
        assert is_valid_jalali_date(1404, 12, 30) is False

    def test_roundtrip_display(self):
        g = jalali_to_gregorian_str("1403/05/02")
        assert gregorian_to_jalali_str(g) == "1403-05-02"