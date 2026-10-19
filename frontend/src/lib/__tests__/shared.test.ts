// مجموعه داده آزمون مشترک با بک‌اند (قاعده سند §۳۲: واگرایی اعتبارسنجی مرورگر/سرور نباید رخ دهد)
import { describe, expect, it } from 'vitest';
import {
  normalizeDigits, isValidNationalId, isValidMobile, normalizeMobile,
  jalaliToGregorianStr, gregorianToJalaliStr,
} from '../persian';
import { evaluateFormula, evaluateCondition } from '../formula';

describe('ابزارهای ایرانی (قرینه بک‌اند)', () => {
  it('یکسان‌سازی ارقام فارسی/عربی', () => {
    expect(normalizeDigits('۰۱۲۳۴۵۶۷۸۹')).toBe('0123456789');
    expect(normalizeDigits('٠١٢٣٤٥٦٧٨٩')).toBe('0123456789');
    expect(normalizeDigits('  ۰۹۱۲  ')).toBe('0912');
    expect(normalizeDigits('۰۰۴۹۹۱۲۳۴۵')).toBe('0049912345'); // حفظ صفر ابتدایی
  });

  it('کد ملی — الگوریتم رقم کنترل', () => {
    expect(isValidNationalId('0684159414')).toBe(true);
    expect(isValidNationalId('۰۶۸۴۱۵۹۴۱۴')).toBe(true);
    expect(isValidNationalId('0684159415')).toBe(false);
    expect(isValidNationalId('1111111111')).toBe(false);
    expect(isValidNationalId('12345')).toBe(false);
  });

  it('موبایل — ^09[0-9]{9}$ پس از یکسان‌سازی', () => {
    expect(isValidMobile('09123456789')).toBe(true);
    expect(isValidMobile('۰۹۱۲۳۴۵۶۷۸۹')).toBe(true);
    expect(isValidMobile('+989123456789')).toBe(true);
    expect(normalizeMobile('+989123456789')).toBe('09123456789');
    expect(isValidMobile('0912345678')).toBe(false);
    expect(isValidMobile('08123456789')).toBe(false);
  });

  it('تاریخ جلالی — تبدیل و کبیسه', () => {
    expect(jalaliToGregorianStr('1403/05/02')).toBe('2024-07-23');
    expect(jalaliToGregorianStr('۱۴۰۳/۰۵/۰۲')).toBe('2024-07-23');
    expect(gregorianToJalaliStr('2024-07-23')).toBe('1403/05/02');
  });
});

describe('فرمول‌ساز امن (بدون eval)', () => {
  it('محاسبات و ارجاع فیلد', () => {
    expect(evaluateFormula('2 + 3 * 4', () => 0)).toBe(14);
    expect(evaluateFormula('qty * price', (k) => ({ qty: 3, price: 15000 } as any)[k])).toBe(45000);
  });

  it('SUM روی زیرفرم', () => {
    const rows = [{ row_total: 1000 }, { row_total: 2500 }, { row_total: 500 }];
    expect(evaluateFormula('SUM(items.row_total)', (k) => (k === '__list__items' ? rows : null))).toBe(4000);
  });

  it('شرط‌ها', () => {
    expect(evaluateCondition("action == 'approve'", (k) => ({ action: 'approve' } as any)[k])).toBe(true);
    expect(evaluateCondition('total > 10000000', (k) => ({ total: 15000000 } as any)[k])).toBe(true);
  });

  it('منع اجرای کد آزاد', () => {
    expect(evaluateFormula("__import__('os').system('id')", () => null)).toBeNull();
    expect(evaluateFormula('open("/etc/passwd")', () => null)).toBeNull();
  });
});
