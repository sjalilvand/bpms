// ابزارهای ایرانی — قرینه سمت مرورگر از app/modules/forms/persian.py
// مجموعه داده آزمون مشترک با بک‌اند (قاعده سند §۳۲)
import jalaali from 'jalaali-js';

const PERSIAN_DIGITS = '۰۱۲۳۴۵۶۷۸۹';
const ARABIC_DIGITS = '٠١٢٣٤٥٦٧٨٩';

export function normalizeDigits(value: string | null | undefined): string {
  if (value === null || value === undefined) return '';
  let out = '';
  for (const ch of String(value).trim()) {
    const pi = PERSIAN_DIGITS.indexOf(ch);
    if (pi >= 0) { out += String(pi); continue; }
    const ai = ARABIC_DIGITS.indexOf(ch);
    if (ai >= 0) { out += String(ai); continue; }
    out += ch;
  }
  return out;
}

export function normalizeNationalId(value: string | null | undefined): string {
  return normalizeDigits(value).replace(/-/g, '').replace(/_/g, '');
}

// الگوریتم رقم کنترل کد ملی
export function isValidNationalId(value: string | null | undefined): boolean {
  const v = normalizeNationalId(value);
  if (!/^\d{10}$/.test(v)) return false;
  if (/^(\d)\1{9}$/.test(v)) return false; // ده رقم یکسان
  const d = v.split('').map(Number);
  const s = d[0] * 10 + d[1] * 9 + d[2] * 8 + d[3] * 7 + d[4] * 6 + d[5] * 5 + d[6] * 4 + d[7] * 3 + d[8] * 2;
  const r = s % 11;
  const expected = r < 2 ? r : 11 - r;
  return d[9] === expected;
}

export function normalizeMobile(value: string | null | undefined): string {
  let v = normalizeDigits(value).replace(/-/g, '').replace(/ /g, '');
  if (v.startsWith('+98')) v = '0' + v.slice(3);
  else if (v.startsWith('0098')) v = '0' + v.slice(4);
  else if (v.startsWith('98') && v.length === 12) v = '0' + v.slice(2);
  return v;
}

export function isValidMobile(value: string | null | undefined): boolean {
  return /^09\d{9}$/.test(normalizeMobile(value || ''));
}

// ---------- تقویم جلالی ----------
export function jalaliToGregorianStr(value: string | null | undefined): string | null {
  const v = normalizeDigits(value).replace(/-/g, '/').trim();
  if (!v) return null;
  const parts = v.split('/').filter((p) => p !== '');
  if (parts.length !== 3) return null;
  const y = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10);
  const d = parseInt(parts[2], 10);
  if (!isValidJalaliDate(y, m, d)) return null;
  const g = jalaali.toGregorian(y, m, d);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${g.gy}-${pad(g.gm)}-${pad(g.gd)}`;
}

export function gregorianToJalaliStr(value: string | null | undefined, withTime = false): string | null {
  if (!value) return null;
  const s = String(value);
  try {
    if (s.includes('T')) {
      const dt = new Date(s);
      const j = jalaali.toJalaali(dt.getFullYear(), dt.getMonth() + 1, dt.getDate());
      const pad = (n: number) => String(n).padStart(2, '0');
      const base = `${j.jy}/${pad(j.jm)}/${pad(j.jd)}`;
      if (withTime) return `${base} ${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
      return base;
    }
    const [y, m, d] = s.slice(0, 10).split('-').map(Number);
    const j = jalaali.toJalaali(y, m, d);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${j.jy}/${pad(j.jm)}/${pad(j.jd)}`;
  } catch {
    return null;
  }
}

export function isValidJalaliDate(y: number, m: number, d: number): boolean {
  try {
    return jalaali.isValidJalaaliDate(y, m, d);
  } catch {
    return false;
  }
}

// نمایش عدد با جداکننده هزارگان
export function formatMoney(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === '') return '';
  const n = typeof v === 'string' ? parseFloat(v.replace(/,/g, '')) : v;
  if (isNaN(n)) return String(v);
  return n.toLocaleString('fa-IR');
}
