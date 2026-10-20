// انواع مشترک Schema فرم و اعتبارسنجی سمت مرورگر (بازخورد سریع — مرجع نهایی سرور است)
import { isValidNationalId, isValidMobile, jalaliToGregorianStr } from './persian';
import { evaluateFormula } from './formula';

export interface FormField {
  key: string;
  type: string;
  label?: string;
  required?: boolean;
  help?: string;
  placeholder?: string;
  colSpan?: number;
  readOnly?: boolean;
  minLength?: number;
  maxLength?: number;
  min?: number;
  max?: number;
  decimalPlaces?: number;
  pattern?: string;
  moneyUnit?: string;
  lookupId?: number | null;
  multiple?: boolean;
  options?: { value: string | number; label: string }[];
  minDate?: string;
  maxDate?: string;
  formula?: string;
  subformId?: number | null;
  singleRow?: boolean;
  minRows?: number;
  maxRows?: number;
  compareField?: string;
  compareOp?: string;
  compareMessage?: string;
  visibleIf?: string;
  defaultValue?: string;
}

export interface FormSchema {
  title?: string;
  fields: FormField[];
  theme?: FormTheme;
}

// تم و ظاهر فرم — در فرم‌ساز و نمایش‌دهنده اعمال می‌شود
export interface FormTheme {
  primary?: string;      // رنگ اصلی دکمه‌ها و کنترل‌ها
  headerBg?: string;     // پس‌زمینه سرصفحه فرم
  headerColor?: string;  // رنگ متن سرصفحه
  background?: string;   // پس‌زمینه بدنه فرم
  fieldBg?: string;      // پس‌زمینه فیلدها
  labelColor?: string;   // رنگ برچسب‌ها
  radius?: number;       // گردی گوشه‌ها
  font?: string;         // فونت (پیش‌فرض Vazirmatn)
  density?: 'comfortable' | 'compact';
}

// پیش‌تنم‌های آماده تم — در فرم‌ساز قابل انتخاب
export const THEME_PRESETS: { key: string; name: string; theme: FormTheme }[] = [
  {
    key: 'teal', name: 'فیروزه‌ای سازمانی (پیش‌فرض)',
    theme: { primary: '#0e7490', headerBg: 'linear-gradient(135deg,#0e7490,#155e75)', headerColor: '#ffffff', background: '#f8fafc', fieldBg: '#ffffff', labelColor: '#0f172a', radius: 8, density: 'comfortable' },
  },
  {
    key: 'indigo', name: 'نیلی مدرن',
    theme: { primary: '#4f46e5', headerBg: 'linear-gradient(135deg,#4f46e5,#7c3aed)', headerColor: '#ffffff', background: '#eef2ff', fieldBg: '#ffffff', labelColor: '#1e1b4b', radius: 12, density: 'comfortable' },
  },
  {
    key: 'emerald', name: 'سبز طبیعت',
    theme: { primary: '#059669', headerBg: 'linear-gradient(135deg,#059669,#047857)', headerColor: '#ffffff', background: '#ecfdf5', fieldBg: '#ffffff', labelColor: '#064e3b', radius: 10, density: 'comfortable' },
  },
  {
    key: 'royal', name: 'آبی سلطنتی',
    theme: { primary: '#1d4ed8', headerBg: 'linear-gradient(135deg,#1d4ed8,#1e3a8a)', headerColor: '#ffffff', background: '#eff6ff', fieldBg: '#ffffff', labelColor: '#172554', radius: 6, density: 'comfortable' },
  },
  {
    key: 'rose', name: 'سرخابی گرم',
    theme: { primary: '#e11d48', headerBg: 'linear-gradient(135deg,#e11d48,#be123c)', headerColor: '#ffffff', background: '#fff1f2', fieldBg: '#ffffff', labelColor: '#4c0519', radius: 14, density: 'comfortable' },
  },
  {
    key: 'dark', name: 'تیره اداری',
    theme: { primary: '#f59e0b', headerBg: 'linear-gradient(135deg,#1e293b,#0f172a)', headerColor: '#fbbf24', background: '#f1f5f9', fieldBg: '#ffffff', labelColor: '#0f172a', radius: 8, density: 'compact' },
  },
  {
    key: 'minimal', name: 'مینیمال روشن',
    theme: { primary: '#334155', headerBg: '#f1f5f9', headerColor: '#0f172a', background: '#ffffff', fieldBg: '#ffffff', labelColor: '#334155', radius: 4, density: 'compact' },
  },
];

export const DEFAULT_THEME: FormTheme = THEME_PRESETS[0].theme;

export interface FieldError {
  key: string;
  message: string;
}

export const FIELD_TYPES: Record<string, { label: string; group: string }> = {
  text: { label: 'متن کوتاه', group: 'متنی' },
  textarea: { label: 'متن بلند', group: 'متنی' },
  number: { label: 'عدد اعشاری', group: 'عددی' },
  integer: { label: 'عدد صحیح', group: 'عددی' },
  money: { label: 'مبلغ', group: 'عددی' },
  percent: { label: 'درصد', group: 'عددی' },
  jalali_date: { label: 'تاریخ (جلالی)', group: 'زمانی' },
  time: { label: 'ساعت', group: 'زمانی' },
  national_id: { label: 'کد ملی', group: 'ایرانی' },
  mobile: { label: 'شماره موبایل', group: 'ایرانی' },
  email: { label: 'ایمیل', group: 'متنی' },
  select: { label: 'انتخاب تکی', group: 'انتخابی' },
  multiselect: { label: 'انتخاب چندگانه', group: 'انتخابی' },
  checkbox: { label: 'چک‌باکس', group: 'انتخابی' },
  checkgroup: { label: 'گروه چک‌باکس', group: 'انتخابی' },
  radio: { label: 'رادیوگروه', group: 'انتخابی' },
  user: { label: 'انتخاب کاربر', group: 'سازمانی' },
  org_unit: { label: 'انتخاب واحد سازمانی', group: 'سازمانی' },
  file: { label: 'فایل پیوست', group: 'فایل' },
  calculated: { label: 'محاسباتی', group: 'محاسباتی' },
  subform: { label: 'زیرفرم تکرارشونده', group: 'ساختاری' },
  subform_single: { label: 'زیرفرم تک‌نمونه‌ای', group: 'ساختاری' },
  title: { label: 'عنوان بخش', group: 'نمایشی' },
  help: { label: 'راهنما', group: 'نمایشی' },
  divider: { label: 'جداکننده', group: 'نمایشی' },
  summary: { label: 'خلاصه درخواست', group: 'نمایشی' },
};

// اعتبارسنجی مرورگر — همان قواعد سرور (واگرا نشود؛ تست مشترک)
export function validateFieldClient(field: FormField, value: unknown): string | null {
  const empty = value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0);
  if (empty) {
    return field.required ? `«${field.label || field.key}» الزامی است` : null;
  }
  switch (field.type) {
    case 'national_id':
      if (!isValidNationalId(String(value))) return 'کد ملی واردشده معتبر نیست';
      break;
    case 'mobile':
      if (!isValidMobile(String(value))) return 'شماره موبایل باید با 09 شروع شده و ۱۱ رقم باشد';
      break;
    case 'email':
      if (!/^[\w.+-]+@[\w-]+\.[\w.-]+$/.test(String(value))) return 'نشانی ایمیل معتبر نیست';
      break;
    case 'text':
    case 'textarea': {
      const v = String(value);
      if (field.minLength && v.length < field.minLength) return `حداقل ${field.minLength} نویسه لازم است`;
      if (field.maxLength && v.length > field.maxLength) return `حداکثر ${field.maxLength} نویسه مجاز است`;
      break;
    }
    case 'number':
    case 'integer':
    case 'money':
    case 'percent': {
      const n = typeof value === 'number' ? value : parseFloat(String(value).replace(/,/g, ''));
      if (isNaN(n)) return 'مقدار عددی نامعتبر است';
      if (field.min !== undefined && n < field.min) return `حداقل مقدار مجاز ${field.min} است`;
      if (field.max !== undefined && n > field.max) return `حداکثر مقدار مجاز ${field.max} است`;
      break;
    }
    case 'jalali_date': {
      const g = jalaliToGregorianStr(String(value));
      if (!g) return 'تاریخ نامعتبر است';
      break;
    }
    case 'time':
      if (!/^\d{2}:\d{2}(:\d{2})?$/.test(String(value))) return 'ساعت نامعتبر است';
      break;
    default:
      break;
  }
  return null;
}

// محاسبه فرمول روی داده (پیش‌نمایش مرورگر)
export function computeFormula(expr: string, data: Record<string, unknown>): unknown {
  return evaluateFormula(expr, (key: string) => {
    if (key.startsWith('__list__')) {
      const arr = data[key.slice('__list__'.length)];
      return Array.isArray(arr) ? arr : [];
    }
    return data[key];
  });
}
