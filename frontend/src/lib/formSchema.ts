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
}

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
