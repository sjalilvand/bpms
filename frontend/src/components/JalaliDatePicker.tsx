// انتخابگر تاریخ جلالی — مقدار ذخیره‌شده میلادی ISO، نمایش جلالی
import React from 'react';
import DatePicker_ from 'react-multi-date-picker';
import persian from 'react-date-object/calendars/persian';
import persian_fa from 'react-date-object/locales/persian_fa';
import { Form } from 'antd';

interface Props {
  value?: string | null;
  onChange?: (v: string | null) => void;
  disabled?: boolean;
  placeholder?: string;
}

// سازگار با antd Form.Item (value/onChange)
export default function JalaliDatePicker({ value, onChange, disabled, placeholder }: Props) {
  return (
    <span data-testid="jalali-datepicker" style={{ display: 'block' }}>
      <DatePicker_
      calendar={persian}
      locale={persian_fa}
      value={value ? value : ''}
      onChange={(d: any) => {
        if (!d) { onChange?.(null); return; }
        const gy = d.year, gm = String(d.month.number).padStart(2, '0'), gd = String(d.day).padStart(2, '0');
        onChange?.(`${gy}-${gm}-${gd}`);
      }}
      disabled={disabled}
      placeholder={placeholder || 'انتخاب تاریخ'}
      containerStyle={{ width: '100%' }}
      style={{ width: '100%', fontFamily: "'Vazirmatn', sans-serif", height: 32, borderRadius: 8, border: '1px solid #d9d9d9', padding: '0 11px' }}
      calendarPosition="bottom-right"
    />
    </span>
  );
}
