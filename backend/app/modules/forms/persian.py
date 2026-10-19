# -*- coding: utf-8 -*-
"""ابزارهای اختصاصی ایران: یکسان‌سازی ارقام، کد ملی، شماره موبایل، تقویم جلالی.

قواعد سند:
- ارقام فارسی/عربی به انگلیسی تبدیل شود؛ صفر ابتدایی حفظ شود (ذخیره به‌صورت رشته).
- کد ملی: ده‌رقمی، الگوریتم رقم کنترل؛ ده رقم یکسان رد می‌شود.
- موبایل: ^09[0-9]{9}$ پس از یکسان‌سازی.
- تاریخ جلالی: تبدیل آزموده‌شده به میلادی.
"""
from __future__ import annotations

import re
import jdatetime
from datetime import date, datetime

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_DIGIT_MAP = {ord(p): str(i) for i, p in enumerate(PERSIAN_DIGITS)}
_DIGIT_MAP.update({ord(a): str(i) for i, a in enumerate(ARABIC_DIGITS)})

MOBILE_RE = re.compile(r"^09\d{9}$")
NATIONAL_ID_RE = re.compile(r"^\d{10}$")


def normalize_digits(value: str | None) -> str:
    """تبدیل ارقام فارسی/عربی به انگلیسی + حذف فاصله ابتدا و انتها."""
    if value is None:
        return ""
    return str(value).translate(_DIGIT_MAP).strip()


def normalize_national_id(value: str | None) -> str:
    """یکسان‌سازی + حذف جداکننده‌های متداول. حذف خودکار نویسه‌های نامعتبر انجام نمی‌شود."""
    v = normalize_digits(value).replace("-", "").replace("_", "")
    return v


def is_valid_national_id(value: str | None) -> bool:
    """اعتبارسنجی کد ملی مطابق الگوریتم رقم کنترل.

    S = d1×10 + d2×9 + ... + d9×2
    R = S mod 11
    اگر R < 2 → d10 = R ؛ وگرنه d10 = 11 - R
    عبور از این آزمون وجود واقعی کد را اثبات نمی‌کند.
    """
    v = normalize_national_id(value)
    if not NATIONAL_ID_RE.match(v):
        return False
    if v == v[0] * 10:  # ده رقم یکسان
        return False
    digits = [int(c) for c in v]
    s = sum(digits[i] * (10 - i) for i in range(9))
    r = s % 11
    expected = r if r < 2 else 11 - r
    return digits[9] == expected


def normalize_mobile(value: str | None) -> str:
    """یکسان‌سازی موبایل؛ پشتیبانی از قالب +98 در صورت فعال‌بودن تبدیل."""
    v = normalize_digits(value).replace("-", "").replace(" ", "")
    if v.startswith("+98"):
        v = "0" + v[3:]
    elif v.startswith("0098"):
        v = "0" + v[4:]
    elif v.startswith("98") and len(v) == 12:
        v = "0" + v[2:]
    return v


def is_valid_mobile(value: str | None) -> bool:
    return bool(MOBILE_RE.match(normalize_mobile(value or "")))


# ---------- تقویم جلالی ----------
def is_valid_jalali_date(y: int, m: int, d: int) -> bool:
    """کنترل اعتبار روز و ماه جلالی (شامل کبیسه)."""
    try:
        jdatetime.date(y, m, d)
        return True
    except (ValueError, OverflowError):
        return False


def jalali_to_gregorian_str(value: str | None) -> str | None:
    """ورودی: '1403/05/02' یا '1403-5-2' (ارقام فارسی مجاز) → خروجی ISO میلادی.

    تاریخ بدون ساعت، بدون تبدیل منطقه زمانی ذخیره می‌شود (قاعده سند).
    """
    v = normalize_digits(value).replace("-", "/").strip()
    if not v:
        return None
    parts = [p for p in v.split("/") if p != ""]
    if len(parts) != 3:
        return None
    try:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        if not is_valid_jalali_date(y, m, d):
            return None
        return jdatetime.date(y, m, d).togregorian().isoformat()
    except (ValueError, OverflowError):
        return None


def gregorian_to_jalali_str(value: str | date | datetime | None, with_time: bool = False) -> str | None:
    """نمایش جلالی مقدار ذخیره‌شده میلادی."""
    if value in (None, ""):
        return None
    if isinstance(value, str):
        v = value.strip()
        try:
            if "T" in v:
                dt = datetime.fromisoformat(v)
                j = jdatetime.date.fromgregorian(date=dt.date())
                if with_time:
                    return f"{j.isoformat()} {dt.strftime('%H:%M')}"
                return j.isoformat()
            d = date.fromisoformat(v[:10])
        except ValueError:
            return None
    elif isinstance(value, datetime):
        j = jdatetime.date.fromgregorian(date=value.date())
        return j.isoformat() if not with_time else f"{jdatetime.date.fromgregorian(date=value.date()).isoformat()} {value.strftime('%H:%M')}"
    else:
        d = value
        j = jdatetime.date.fromgregorian(date=d)
        return j.isoformat()
    j = jdatetime.date.fromgregorian(date=d)
    return j.isoformat()
