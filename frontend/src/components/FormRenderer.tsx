// نمایش‌دهنده فرم — اجرای تعریف منتشرشده در همه محیط‌ها (پیش‌نمایش/شروع/وظیفه/مشاهده)
// مجوز نهایی هر اجرا از سرور دریافت می‌شود؛ این جزء جایگزین کنترل دسترسی نیست.
import React, { useEffect, useMemo, useState } from 'react';
import {
  Button, Checkbox, Col, DatePicker, Divider, Descriptions, Form, Input, InputNumber,
  Popover, Radio, Row, Select, Space, TreeSelect, Upload, Typography, Alert,
} from 'antd';
import { DeleteOutlined, PlusOutlined, PaperClipOutlined } from '@ant-design/icons';
import type { FormSchema, FormField } from '../lib/formSchema';
import { validateFieldClient, computeFormula } from '../lib/formSchema';
import { evaluateCondition } from '../lib/formula';
import { gregorianToJalaliStr, normalizeNationalId, normalizeMobile, formatMoney } from '../lib/persian';
import { api } from '../api/client';
import JalaliDatePicker from './JalaliDatePicker';

const { TextArea } = Input;
const { Title, Text } = Typography;

export interface OptionItem {
  id: number | string;
  title: string;
  parent_id?: number | null;
  children?: OptionItem[];
}

interface Props {
  schema: FormSchema;
  initialValues?: Record<string, unknown>;
  readOnly?: boolean;
  submitting?: boolean;
  hideActions?: boolean;
  submitText?: string;
  submitResults?: { value: string; label: string }[];
  onFinish?: (values: Record<string, unknown>, result?: string) => void;
  formRef?: React.MutableRefObject<any>;
}

export default function FormRenderer({
  schema, initialValues, readOnly, submitting, hideActions,
  submitText = 'ثبت', submitResults, onFinish, formRef,
}: Props) {
  const [form] = Form.useForm();
  const ref = formRef || React.useRef<any>(form);
  useEffect(() => { if (formRef) formRef.current = form; }, [form]);
  const [lookups, setLookups] = useState<Record<number, OptionItem[]>>({});
  const [users, setUsers] = useState<{ id: number; full_name: string }[]>([]);
  const [orgTree, setOrgTree] = useState<any[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  // تیک همگام‌سازی ذخیره فرم — زیرفرم‌ها مقدار را برنامه‌ای می‌نویسند و useWatch آن‌ها را نمی‌بیند
  const [storeTick, setStoreTick] = useState(0);

  useEffect(() => {
    if (initialValues) form.setFieldsValue(initialValues);
  }, [JSON.stringify(initialValues || {})]);

  // منابع داده کنترل‌ها
  useEffect(() => {
    const ids = new Set<number>();
    (schema.fields || []).forEach((f) => { if (f.lookupId) ids.add(f.lookupId); });
    ids.forEach((id) => {
      api.get(`/lookups/${id}/items`).then((r) => {
        const flat: OptionItem[] = [];
        const walk = (items: OptionItem[]) => items.forEach((it) => {
          flat.push(it);
          if (it.children?.length) walk(it.children as unknown as OptionItem[]);
        });
        walk(r.data.items);
        setLookups((prev) => ({ ...prev, [id]: flat }));
      }).catch(() => {});
    });
    const needsUsers = (schema.fields || []).some((f) => f.type === 'user');
    if (needsUsers) api.get('/users', { params: { page_size: 200 } }).then((r) => setUsers(r.data.items)).catch(() => {});
    const needsOrg = (schema.fields || []).some((f) => f.type === 'org_unit');
    if (needsOrg) api.get('/org-units').then((r) => setOrgTree(r.data.items)).catch(() => {});
  }, [JSON.stringify(schema)]);

  const watched = Form.useWatch([], form);
  // ادغام مقادیر watch شده با ذخیره کامل — منبع حقیقت برای فرمول‌ها
  const values = useMemo(() => ({ ...(watched || {}), ...(form.getFieldsValue(true) || {}) }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(watched || {}), storeTick]);

  // محاسبه فرمول‌ها برای نمایش زنده
  const computed = useMemo(() => {
    const out: Record<string, unknown> = {};
    const plain: Record<string, unknown> = { ...values };
    (schema.fields || []).forEach((f) => {
      if (f.type === 'calculated' && f.formula) {
        out[f.key] = computeFormula(f.formula, plain);
      }
    });
    return out;
  }, [values, JSON.stringify(schema)]);

  const visible = (f: FormField) => !f.visibleIf || evaluateVisible(f.visibleIf, values);

  const validateAll = (): Record<string, unknown> | null => {
    const errs: Record<string, string> = {};
    const data: Record<string, unknown> = form.getFieldsValue(true) || {};
    for (const f of schema.fields || []) {
      if (!f.key || ['title', 'help', 'divider', 'summary'].includes(f.type)) continue;
      if (!visible(f)) continue;
      const msg = validateFieldClient(f, data[f.key]);
      if (msg) errs[f.key] = msg;
      if (f.type === 'subform' && Array.isArray(data[f.key])) {
        const rows = data[f.key] as Record<string, unknown>[];
        if (!rows.length && f.minRows && f.minRows > 0) errs[f.key] = `حداقل ${f.minRows} ردیف لازم است`;
        rows.forEach((row, i) => {
          for (const sf of subSchemaCache[f.subformId || -1]?.fields || []) {
            const m = validateFieldClient(sf, row[sf.key]);
            if (m) { errs[`${f.key}[${i}].${sf.key}`] = m; }
          }
        });
      }
    }
    setErrors(errs);
    return Object.keys(errs).length ? null : data;
  };

  const finish = (result?: string) => {
    const data = validateAll();
    if (!data) return;
    const cleaned = { ...data };
    // محاسبه نهایی فرمول‌ها روی ذخیره کامل (شامل زیرفرم‌ها) — نه مقادیر watch شده
    for (const f of schema.fields || []) {
      if (f.type === 'national_id' && cleaned[f.key]) cleaned[f.key] = normalizeNationalId(String(cleaned[f.key]));
      if (f.type === 'mobile' && cleaned[f.key]) cleaned[f.key] = normalizeMobile(String(cleaned[f.key]));
      if (f.type === 'calculated') cleaned[f.key] = computeFormula(f.formula || '', { ...data });
    }
    onFinish?.(cleaned, result);
  };

  const subSchemaCache: Record<number, FormSchema> = (window as any).__bpms_subschemas__ || {};

  const renderField = (f: FormField) => {
    const span = f.colSpan || 12;
    if (f.type === 'title') return <Col key={f.key || Math.random()} span={24}><Title level={5} style={{ margin: '8px 0 0' }}>{f.label}</Title></Col>;
    if (f.type === 'help') return <Col key={f.key || Math.random()} span={24}><Text type="secondary">{f.label}</Text></Col>;
    if (f.type === 'divider') return <Col key={f.key || Math.random()} span={24}><Divider style={{ margin: '8px 0' }} /></Col>;
    if (f.type === 'summary') return <Col key={f.key || Math.random()} span={24}><SummaryBlock data={{ ...values, ...computed }} schema={schema} /></Col>;

    if (!f.key) return null;

    const isReadOnly = readOnly || f.readOnly;
    const err = errors[f.key];

    let control: React.ReactNode;
    switch (f.type) {
      case 'text':
        control = <Input placeholder={f.placeholder} maxLength={f.maxLength} disabled={isReadOnly} />;
        break;
      case 'textarea':
        control = <TextArea rows={3} placeholder={f.placeholder} maxLength={f.maxLength} disabled={isReadOnly} />;
        break;
      case 'email':
        control = <Input placeholder="name@example.com" disabled={isReadOnly} />;
        break;
      case 'national_id':
        control = <Input placeholder="کد ملی ۱۰ رقمی" maxLength={12} disabled={isReadOnly} />;
        break;
      case 'mobile':
        control = <Input placeholder="09xxxxxxxxx" maxLength={14} disabled={isReadOnly} />;
        break;
      case 'number':
      case 'integer':
      case 'money':
      case 'percent': {
        const isMoney = f.type === 'money';
        control = (
          <InputNumber
            style={{ width: '100%' }} min={f.min} max={f.max} precision={f.decimalPlaces ?? (f.type === 'integer' ? 0 : undefined)}
            formatter={(v) => (isMoney ? `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',') : `${v}`)}
            parser={(v) => (v ? Number(v.replace(/,/g, '')) as any : 0 as any)}
            disabled={isReadOnly} addonAfter={isMoney ? (f.moneyUnit || 'ریال') : f.type === 'percent' ? '٪' : undefined}
          />
        );
        break;
      }
      case 'jalali_date':
        control = <JalaliDatePicker disabled={isReadOnly} />;
        break;
      case 'time':
        control = <Input placeholder="HH:MM" disabled={isReadOnly} />;
        break;
      case 'select':
      case 'multiselect': {
        let opts = (f.options || []).map((o) => ({ value: o.value as any, label: o.label }));
        if (f.lookupId && lookups[f.lookupId]) {
          const items = lookups[f.lookupId];
          opts = items.map((it) => ({ value: it.id as any, label: it.title }));
        }
        control = (
          <Select
            mode={f.type === 'multiselect' ? 'multiple' : undefined}
            placeholder="انتخاب کنید" allowClear disabled={isReadOnly} showSearch optionFilterProp="label"
            options={opts}
          />
        );
        break;
      }
      case 'radio': {
        const opts = (f.options || []).map((o) => ({ value: o.value as any, label: o.label }));
        control = <Radio.Group disabled={isReadOnly} options={opts} />;
        break;
      }
      case 'checkgroup': {
        const opts = (f.options || []).map((o) => ({ value: o.value as any, label: o.label }));
        control = <Checkbox.Group disabled={isReadOnly} options={opts} />;
        break;
      }
      case 'checkbox':
        control = <Checkbox disabled={isReadOnly}>{f.label}</Checkbox>;
        break;
      case 'user':
        control = (
          <Select placeholder="انتخاب کاربر" showSearch optionFilterProp="label" allowClear disabled={isReadOnly}
            options={users.map((u) => ({ value: u.id, label: u.full_name }))} />
        );
        break;
      case 'org_unit':
        control = (
          <TreeSelect
            treeData={orgTree} fieldNames={{ label: 'name', value: 'id', children: 'children' }}
            placeholder="انتخاب واحد" allowClear showSearch treeNodeFilterProp="name" disabled={isReadOnly}
          />
        );
        break;
      case 'file':
        control = <FileField disabled={isReadOnly} />;
        break;
      case 'calculated':
        return (
          <Col key={f.key} span={span}>
            <Form.Item label={`${f.label}${f.moneyUnit ? ` (${f.moneyUnit})` : ''}`}>
              <Text strong style={{ fontSize: 16 }}>
                {f.moneyUnit ? formatMoney(computed[f.key] as number) : String(computed[f.key] ?? '—')}
              </Text>
              {f.moneyUnit ? <Text type="secondary" style={{ marginRight: 6 }}>{f.moneyUnit}</Text> : null}
            </Form.Item>
          </Col>
        );
      case 'subform':
        return (
          <Col key={f.key} span={24}>
            <SubformField
              field={f} readOnly={isReadOnly} values={values}
              onSync={() => setStoreTick((t) => t + 1)}
              onSchemasLoaded={(id, s) => { subSchemaCache[id] = s; }}
            />
          </Col>
        );
      case 'subform_single':
        return (
          <Col key={f.key} span={24}>
            <SubformSingle field={f} readOnly={isReadOnly}
              onSync={() => setStoreTick((t) => t + 1)}
              onSchemasLoaded={(id, s) => { subSchemaCache[id] = s; }} />
          </Col>
        );
      default:
        control = <Input disabled={isReadOnly} />;
    }

    return (
      <Col key={f.key} span={span}>
        {f.type === 'checkbox' ? (
          <Form.Item name={f.key} valuePropName="checked">
            {control}
          </Form.Item>
        ) : (
          <Form.Item
            name={f.key}
            label={f.type === 'checkbox' ? undefined : f.label}
            help={err || f.help}
            validateStatus={err ? 'error' : undefined}
            extra={f.moneyUnit && f.type !== 'money' ? f.moneyUnit : undefined}
          >
            {control}
          </Form.Item>
        )}
      </Col>
    );
  };

  return (
    <Form form={form} layout="vertical" onFinish={() => finish()}>
      <Row gutter={16}>
        {(schema.fields || []).filter(visible).map(renderField)}
      </Row>
      {Object.keys(errors).some((k) => k.includes('.')) && (
        <Alert type="error" showIcon style={{ marginTop: 8 }}
          message="برخی ردیف‌های زیرفرم خطا دارند؛ موارد مشخص‌شده را اصلاح کنید" />
      )}
      {!hideActions && !readOnly && (
        <div style={{ marginTop: 16 }}>
          {submitResults?.length ? (
            <Space wrap>
              {submitResults.map((r) => (
                <Button key={r.value} type={r.value === 'approve' ? 'primary' : 'default'}
                  danger={r.value === 'reject'} loading={submitting}
                  onClick={() => finish(r.value)}>
                  {r.label}
                </Button>
              ))}
            </Space>
          ) : (
            <Button type="primary" htmlType="submit" loading={submitting}>{submitText}</Button>
          )}
        </div>
      )}
    </Form>
  );
}

function evaluateVisible(cond: string, values: Record<string, unknown>): boolean {
  // شرط نمایش ساده با ارزیاب امن مشترک
  return evaluateCondition(cond, (k) => values[k]);
}

function SummaryBlock({ data, schema }: { data: Record<string, unknown>; schema: FormSchema }) {
  // نمایش داده‌های همه مراحل نمونه (متغیرهای موتور) — کلیدهای داخلی پنهان می‌شوند
  const labels: Record<string, { label: string; type: string; moneyUnit?: string }> = {};
  for (const f of schema.fields || []) {
    if (f.key) labels[f.key] = { label: f.label || f.key, type: f.type, moneyUnit: f.moneyUnit };
  }
  const items = Object.entries(data)
    .filter(([k]) => !k.startsWith('_') && !k.endsWith('_jalali'))
    .map(([k, v]) => {
      const meta = labels[k];
      let val: unknown = v;
      if (meta?.type === 'jalali_date') val = gregorianToJalaliStr(String(v || '')) || v;
      else if (meta?.type === 'money') val = `${formatMoney(v as number)} ${meta.moneyUnit || 'ریال'}`;
      else if (typeof v === 'number' && meta?.type !== 'number') val = v;
      if (Array.isArray(v)) val = `${v.length} ردیف`;
      else if (v !== null && typeof v === 'object') val = JSON.stringify(v).slice(0, 80);
      return {
        key: k,
        label: meta?.label || k,
        value: val === null || val === undefined || val === '' ? '—' : String(val),
      };
    });
  return (
    <Descriptions size="small" bordered column={2}>
      {items.map((it) => <Descriptions.Item key={it.key} label={it.label}>{it.value}</Descriptions.Item>)}
    </Descriptions>
  );
}

function FileField({ disabled }: { disabled?: boolean }) {
  const [fileId, setFileId] = useState<number | null>(null);
  const [name, setName] = useState<string>('');
  return (
    <Space>
      <Upload
        maxCount={1} disabled={disabled}
        action="/api/v1/attachments"
        headers={{ Authorization: `Bearer ${localStorage.getItem('bpms_token') || ''}` }}
        onChange={(info) => {
          if (info.file.status === 'done') {
            setFileId(info.file.response?.id);
            setName(info.file.response?.name);
          }
        }}
        showUploadList={false}
      >
        <Button icon={<PaperClipOutlined />} disabled={disabled}>انتخاب فایل</Button>
      </Upload>
      {name && <Text type="secondary">{name} (#{fileId})</Text>}
    </Space>
  );
}

// ---------- زیرفرم تکرارشونده (state محلی + همگام‌سازی با فرم والد) ----------
interface SubformProps {
  field: FormField;
  readOnly?: boolean;
  values?: Record<string, unknown>;
  onSync?: () => void;
  onSchemasLoaded?: (id: number, s: FormSchema) => void;
}

function SubformField({ field, readOnly, onSync }: SubformProps) {
  const form = Form.useFormInstance();
  const [schema, setSchema] = useState<FormSchema | null>(null);
  const [rows, setRows] = useState<Record<string, unknown>[]>(() => {
    const v = form.getFieldValue(field.key);
    return Array.isArray(v) ? v : [];
  });

  useEffect(() => {
    form.setFieldValue(field.key, rows);
    onSync?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  useEffect(() => {
    if (field.subformId) {
      api.get(`/forms/versions/published-by-form/${field.subformId}`)
        .then((r) => setSchema(r.data.schema_json))
        .catch(() => setSchema(null));
    }
  }, [field.subformId]);

  if (!schema) return <Alert type="warning" message="زیرفرم منتشرشده‌ای برای این فیلد یافت نشد" />;

  const updateRow = (idx: number, key: string, val: unknown) =>
    setRows((rs) => rs.map((r, i) => (i === idx ? { ...r, [key]: val } : r)));
  const addRow = () => setRows((rs) => [...rs, {}]);
  const removeRow = (idx: number) => setRows((rs) => rs.filter((_, i) => i !== idx));

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 12, background: '#fafbfc' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <Text strong>{field.label}</Text>
        {!readOnly && (
          <Button size="small" icon={<PlusOutlined />} onClick={addRow}
            disabled={field.maxRows ? rows.length >= field.maxRows : false}>
            افزودن ردیف
          </Button>
        )}
      </div>
      {rows.length === 0 && <Text type="secondary">ردیفی ثبت نشده است</Text>}
      {rows.map((row, idx) => (
        <div key={idx} style={{ border: '1px dashed #d1d5db', borderRadius: 6, padding: 10, marginBottom: 8, position: 'relative', background: '#fff' }}>
          <Row gutter={12}>
            {schema!.fields.filter((sf) => !['title', 'help', 'divider'].includes(sf.type)).map((sf) => {
              const calcVal = sf.type === 'calculated' ? computeFormula(sf.formula || '', row) : undefined;
              if (sf.type === 'calculated' && row[sf.key] !== calcVal) {
                setTimeout(() => updateRow(idx, sf.key, calcVal), 0);
              }
              return (
                <Col key={sf.key} span={sf.colSpan ? Math.max(4, Math.round(sf.colSpan / 2)) : 6}>
                  <div style={{ marginBottom: 4 }}>
                    <div style={{ fontSize: 12, color: '#4b5563', marginBottom: 2 }}>{sf.label}</div>
                    {sf.type === 'calculated' ? (
                      <Text strong>{sf.moneyUnit ? formatMoney(calcVal as number) : String(calcVal ?? '—')}</Text>
                    ) : sf.type === 'integer' || sf.type === 'number' || sf.type === 'money' ? (
                      <InputNumber
                        data-testid={`sub-${field.key}-${sf.key}-${idx}`}
                        style={{ width: '100%' }} min={sf.min} max={sf.max} disabled={readOnly}
                        value={(row[sf.key] as number) ?? undefined}
                        formatter={(v) => (sf.type === 'money' ? `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',') : `${v}`)}
                        parser={(v) => (v ? (Number(v.replace(/,/g, '')) as any) : (0 as any))}
                        onChange={(v) => updateRow(idx, sf.key, v)}
                      />
                    ) : (
                      <Input
                        data-testid={`sub-${field.key}-${sf.key}-${idx}`}
                        disabled={readOnly} maxLength={sf.maxLength}
                        value={(row[sf.key] as string) ?? ''}
                        onChange={(e) => updateRow(idx, sf.key, e.target.value)}
                      />
                    )}
                  </div>
                </Col>
              );
            })}
          </Row>
          {!readOnly && <Button type="text" danger size="small" icon={<DeleteOutlined />} onClick={() => removeRow(idx)} style={{ position: 'absolute', top: 6, left: 6 }} />}
        </div>
      ))}
      {field.minRows && rows.length < field.minRows && (
        <Text type="danger" style={{ fontSize: 12 }}>حداقل {field.minRows} ردیف لازم است</Text>
      )}
    </div>
  );
}

// ---------- زیرفرم تک‌نمونه‌ای ----------
function SubformSingle({ field, readOnly, onSync }: SubformProps) {
  const form = Form.useFormInstance();
  const [schema, setSchema] = useState<FormSchema | null>(null);
  const [obj, setObj] = useState<Record<string, unknown>>(() => {
    const v = form.getFieldValue(field.key);
    return v && typeof v === 'object' && !Array.isArray(v) ? v : {};
  });

  useEffect(() => {
    form.setFieldValue(field.key, obj);
    onSync?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [obj]);

  useEffect(() => {
    if (field.subformId) {
      api.get(`/forms/versions/published-by-form/${field.subformId}`)
        .then((r) => setSchema(r.data.schema_json))
        .catch(() => setSchema(null));
    }
  }, [field.subformId]);

  if (!schema) return <Alert type="warning" message="زیرفرم منتشرشده‌ای برای این فیلد یافت نشد" />;

  const update = (key: string, val: unknown) => setObj((o) => ({ ...o, [key]: val }));

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 12, background: '#fafbfc' }}>
      <Text strong style={{ display: 'block', marginBottom: 8 }}>{field.label}</Text>
      <Row gutter={12}>
        {schema.fields.filter((sf) => !['title', 'help', 'divider'].includes(sf.type)).map((sf) => (
          <Col key={sf.key} span={sf.colSpan ? Math.min(24, sf.colSpan) : 8}>
            <div style={{ marginBottom: 4 }}>
              <div style={{ fontSize: 12, color: '#4b5563', marginBottom: 2 }}>{sf.label}</div>
              <Input
                disabled={readOnly || sf.readOnly} maxLength={sf.maxLength}
                value={(obj[sf.key] as string) ?? ''}
                onChange={(e) => update(sf.key, e.target.value)}
              />
            </div>
          </Col>
        ))}
      </Row>
    </div>
  );
}
