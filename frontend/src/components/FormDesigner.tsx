// فرم‌ساز — پالت + بوم قابل مرتب‌سازی (dnd-kit) + پنل ویژگی‌ها + پیش‌نمایش
import React, { useMemo, useState } from 'react';
import {
  Button, Card, Col, Divider, Form, Input, InputNumber, Modal, Popconfirm, Row, Select,
  Space, Switch, Tabs, Typography, Alert, App as AntApp, Checkbox,
} from 'antd';
import { DeleteOutlined, EyeOutlined, CopyOutlined } from '@ant-design/icons';
import {
  DndContext, closestCenter, PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core';
import {
  SortableContext, arrayMove, useSortable, verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { FormField, FormSchema } from '../lib/formSchema';
import { FIELD_TYPES } from '../lib/formSchema';
import FormRenderer from './FormRenderer';
import { api } from '../api/client';
import { extractError } from '../api/client';

const { Option } = Select;
const { Text } = Typography;

const PALETTE_GROUPS: { group: string; types: string[] }[] = [
  { group: 'متنی', types: ['text', 'textarea', 'email'] },
  { group: 'عددی', types: ['number', 'integer', 'money', 'percent'] },
  { group: 'زمانی', types: ['jalali_date', 'time'] },
  { group: 'ایرانی', types: ['national_id', 'mobile'] },
  { group: 'انتخابی', types: ['select', 'multiselect', 'radio', 'checkgroup', 'checkbox'] },
  { group: 'سازمانی', types: ['user', 'org_unit'] },
  { group: 'فایل', types: ['file'] },
  { group: 'ساختاری', types: ['subform', 'subform_single'] },
  { group: 'نمایشی', types: ['title', 'help', 'divider', 'summary'] },
  { group: 'محاسباتی', types: ['calculated'] },
];

let seq = 1;
function newField(type: string): FormField {
  const base: FormField = {
    key: `field_${Date.now()}_${seq++}`,
    type,
    label: FIELD_TYPES[type]?.label || type,
    colSpan: type === 'textarea' || type === 'subform' ? 24 : 8,
  };
  if (type === 'calculated') base.formula = '';
  if (type === 'subform' || type === 'subform_single') { base.subformId = null; base.minRows = 1; base.maxRows = 10; }
  if (type === 'radio' || type === 'select' || type === 'multiselect' || type === 'checkgroup') base.options = [{ value: 'a', label: 'گزینه الف' }];
  if (type === 'title' || type === 'help' || type === 'divider' || type === 'summary') base.key = '';
  return base;
}

function SortableField({ field, index, selected, onSelect, onRemove, onCopy }: {
  field: FormField; index: number; selected: boolean;
  onSelect: () => void; onRemove: () => void; onCopy: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: field.key || `__disp_${index}` });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };
  const isStatic = ['title', 'help', 'divider', 'summary'].includes(field.type);
  return (
    <Col span={field.colSpan || 12} style={style}>
      <div
        ref={setNodeRef}
        className="field-card"
        style={{ borderColor: selected ? '#0e7490' : undefined, borderWidth: selected ? 2 : 1 }}
        onClick={onSelect}
        {...attributes} {...listeners}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
          <div style={{ minWidth: 0 }}>
            <Text strong style={{ fontSize: 13 }}>{field.label || FIELD_TYPES[field.type]?.label}</Text>
            <div>
              <Text type="secondary" style={{ fontSize: 11 }} className="mono">{field.key || '—'}</Text>
              {field.required && !isStatic && <Text type="danger" style={{ fontSize: 11 }}> * الزامی</Text>}
              {field.type === 'calculated' && <Text type="secondary" style={{ fontSize: 11 }}> = {field.formula}</Text>}
              {field.type === 'subform' && <Text type="secondary" style={{ fontSize: 11 }}> (زیرفرم #{field.subformId ?? '—'})</Text>}
            </div>
          </div>
          <Space size={0}>
            <Button type="text" size="small" icon={<CopyOutlined />} onClick={(e) => { e.stopPropagation(); onCopy(); }} />
            <Popconfirm title="حذف فیلد؟" onConfirm={(e) => { e?.stopPropagation(); onRemove(); }} onCancel={(e) => e?.stopPropagation()}>
              <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()} />
            </Popconfirm>
          </Space>
        </div>
      </div>
    </Col>
  );
}

interface Props {
  formId: number;
  formTitle: string;
  versionId: number;
  versionStatus: string;
  initialSchema: FormSchema;
  changeNote?: string;
  onSaved?: () => void;
}

export default function FormDesigner({ formId, formTitle, versionId, versionStatus, initialSchema, changeNote, onSaved }: Props) {
  const { message } = AntApp.useApp();
  const [schema, setSchema] = useState<FormSchema>(initialSchema || { fields: [] });
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [formsList, setFormsList] = useState<{ id: number; title: string }[]>([]);
  const sensors = useSensors(useSensor(PointerSensor));

  const isDraft = versionStatus === 'draft';
  const selected: FormField | null = selectedIdx !== null ? schema.fields[selectedIdx] || null : null;

  useMemo(() => {
    api.get('/forms').then((r) => setFormsList(r.data.items.filter((f: any) => f.id !== formId))).catch(() => {});
  }, [formId]);

  const addField = (type: string) => {
    if (!isDraft) { message.warning('فقط نسخه پیش‌نویس قابل ویرایش است؛ ابتدا نسخه جدید بسازید'); return; }
    const f = newField(type);
    setSchema((s) => ({ ...s, fields: [...s.fields, f] }));
    setSelectedIdx(schema.fields.length);
  };

  const patch = (key: keyof FormField, value: unknown) => {
    if (selectedIdx === null) return;
    setSchema((s) => {
      const fields = [...s.fields];
      fields[selectedIdx] = { ...fields[selectedIdx], [key]: value };
      return { ...s, fields };
    });
  };

  const save = async (publish: boolean) => {
    setSaving(true);
    try {
      await api.put(`/forms/versions/${versionId}`, {
        schema_json: schema,
        change_note: changeNote || '',
      });
      if (publish) {
        await api.post(`/forms/versions/${versionId}/publish`);
        message.success('فرم با موفقیت منتشر شد');
      } else {
        message.success('پیش‌نویس ذخیره شد');
      }
      onSaved?.();
    } catch (e) {
      message.error(extractError(e));
    } finally {
      setSaving(false);
    }
  };

  const validateStructure = async () => {
    try {
      const r = await api.post(`/forms/versions/${versionId}/validate-structure`, { schema_json: schema });
      const { errors, warnings } = r.data;
      if (!errors.length && !warnings.length) message.success('ساختار فرم معتبر است');
      else if (errors.length) message.error({ content: `خطا: ${errors.join(' | ')}`, duration: 6 });
      else message.warning({ content: `هشدار: ${warnings.join(' | ')}`, duration: 6 });
    } catch (e) { message.error(extractError(e)); }
  };

  const onDragEnd = ({ active, over }: any) => {
    if (!over || active.id === over.id) return;
    setSchema((s) => {
      const oldIdx = s.fields.findIndex((f, i) => (f.key || `__disp_${i}`) === active.id);
      const newIdx = s.fields.findIndex((f, i) => (f.key || `__disp_${i}`) === over.id);
      if (oldIdx < 0 || newIdx < 0) return s;
      return { ...s, fields: arrayMove(s.fields, oldIdx, newIdx) };
    });
  };

  return (
    <Card
      title={`فرم‌ساز: ${formTitle} ${isDraft ? '(پیش‌نویس)' : '(منتشرشده — فقط-خواندنی)'}`}
      extra={
        <Space wrap>
          <Button onClick={validateStructure}>اعتبارسنجی ساختار</Button>
          <Button icon={<EyeOutlined />} onClick={() => setPreviewOpen(true)}>پیش‌نمایش</Button>
          {isDraft && <Button loading={saving} onClick={() => save(false)}>ذخیره پیش‌نویس</Button>}
          {isDraft && <Button type="primary" loading={saving} onClick={() => save(true)}>انتشار نسخه</Button>}
        </Space>
      }
    >
      {!isDraft && (
        <Alert type="info" showIcon style={{ marginBottom: 12 }}
          message="این نسخه منتشر شده است و تغییرپذیر نیست. برای اصلاح، از صفحه فرم‌ها «ایجاد نسخه جدید» را بزنید." />
      )}
      <Row gutter={12}>
        {/* پالت */}
        <Col span={4}>
          <Card size="small" title="اجزا" styles={{ body: { maxHeight: 560, overflow: 'auto' } }}>
            {PALETTE_GROUPS.map((g) => (
              <div key={g.group}>
                <Divider style={{ margin: '8px 0 4px' }}><Text type="secondary" style={{ fontSize: 11 }}>{g.group}</Text></Divider>
                {g.types.map((t) => (
                  <div key={t} className="palette-item" onClick={() => addField(t)}>
                    {FIELD_TYPES[t].label}
                  </div>
                ))}
              </div>
            ))}
          </Card>
        </Col>

        {/* بوم */}
        <Col span={13}>
          <Card size="small" title={`بوم طراحی (${schema.fields.length} فیلد)`} styles={{ body: { minHeight: 560, maxHeight: 560, overflow: 'auto', background: '#f8fafc' } }}>
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
              <SortableContext items={schema.fields.map((f, i) => f.key || `__disp_${i}`)} strategy={verticalListSortingStrategy}>
                <Row gutter={8}>
                  {schema.fields.map((f, i) => (
                    <SortableField
                      key={f.key || `__disp_${i}`}
                      field={f} index={i}
                      selected={selectedIdx === i}
                      onSelect={() => setSelectedIdx(i)}
                      onRemove={() => {
                        setSchema((s) => ({ ...s, fields: s.fields.filter((_, j) => j !== i) }));
                        setSelectedIdx(null);
                      }}
                      onCopy={() => {
                        const copy = { ...f, key: f.key ? `${f.key}_copy_${Date.now() % 10000}` : '' };
                        setSchema((s) => ({ ...s, fields: [...s.fields.slice(0, i + 1), copy, ...s.fields.slice(i + 1)] }));
                      }}
                    />
                  ))}
                </Row>
              </SortableContext>
            </DndContext>
            {!schema.fields.length && <Alert type="info" message="از پالت سمت راست، جزء موردنظر را به بوم اضافه کنید" />}
          </Card>
        </Col>

        {/* پنل ویژگی‌ها */}
        <Col span={7}>
          <Card size="small" title="ویژگی‌های جزء" styles={{ body: { maxHeight: 560, overflow: 'auto' } }}>
            {!selected && <Alert type="info" message="یک جزء را از بوم انتخاب کنید" />}
            {selected && (
              <Form layout="vertical" size="small">
                {selected.key !== undefined && !['title', 'help', 'divider', 'summary'].includes(selected.type) && (
                  <Form.Item label="نام فنی (پایدار — تغییر آن داده قبلی را از دسترسی خارج می‌کند)">
                    <Input value={selected.key} onChange={(e) => patch('key', e.target.value)} className="mono" />
                  </Form.Item>
                )}
                {selected.type !== 'divider' && (
                  <Form.Item label={selected.type === 'title' ? 'متن عنوان' : 'عنوان/برچسب'}>
                    <Input value={selected.label} onChange={(e) => patch('label', e.target.value)} />
                  </Form.Item>
                )}
                <Row gutter={8}>
                  <Col span={12}>
                    <Form.Item label="عرض (از ۲۴)">
                      <InputNumber min={1} max={24} style={{ width: '100%' }} value={selected.colSpan} onChange={(v) => patch('colSpan', v)} />
                    </Form.Item>
                  </Col>
                  {!['title', 'help', 'divider', 'summary', 'calculated'].includes(selected.type) && (
                    <Col span={12}>
                      <Form.Item label="الزامی">
                        <Checkbox checked={!!selected.required} onChange={(e) => patch('required', e.target.checked)} />
                      </Form.Item>
                    </Col>
                  )}
                </Row>
                {['text', 'textarea'].includes(selected.type) && (
                  <Form.Item label="حداکثر طول">
                    <InputNumber min={1} style={{ width: '100%' }} value={selected.maxLength} onChange={(v) => patch('maxLength', v)} />
                  </Form.Item>
                )}
                {['money', 'number', 'percent'].includes(selected.type) && (
                  <>
                    <Form.Item label="واحد پول (برای مبلغ — صریح)">
                      <Select value={selected.moneyUnit} onChange={(v) => patch('moneyUnit', v)} allowClear>
                        <Option value="ریال">ریال</Option>
                        <Option value="تومان">تومان</Option>
                      </Select>
                    </Form.Item>
                    <Row gutter={8}>
                      <Col span={12}><Form.Item label="حداقل"><InputNumber style={{ width: '100%' }} value={selected.min} onChange={(v) => patch('min', v as any)} /></Form.Item></Col>
                      <Col span={12}><Form.Item label="حداکثر"><InputNumber style={{ width: '100%' }} value={selected.max} onChange={(v) => patch('max', v as any)} /></Form.Item></Col>
                    </Row>
                    <Form.Item label="ارقام اعشار">
                      <InputNumber min={0} max={6} style={{ width: '100%' }} value={selected.decimalPlaces} onChange={(v) => patch('decimalPlaces', v as any)} />
                    </Form.Item>
                  </>
                )}
                {['select', 'multiselect', 'checkgroup', 'radio'].includes(selected.type) && (
                  <Form.Item label="منبع گزینه‌ها">
                    <Select value={selected.lookupId ? `lookup:${selected.lookupId}` : 'static'}
                      onChange={(v) => {
                        if (v === 'static') patch('lookupId', null);
                        else patch('lookupId', parseInt(String(v).split(':')[1], 10));
                      }}>
                      <Option value="static">گزینه‌های ثابت</Option>
                      {formsList.length === 0 && <Option value="none" disabled>— جدول پایه‌ای ثبت نشده —</Option>}
                    </Select>
                  </Form.Item>
                )}
                {['select', 'multiselect', 'radio', 'checkgroup'].includes(selected.type) && !selected.lookupId && (
                  <Form.Item label="گزینه‌ها (نام = عنوان در هر سطر)">
                    <Select
                      mode="tags" style={{ width: '100%' }}
                      value={(selected.options || []).map((o) => `${o.value}=${o.label}`)}
                      onChange={(arr) => patch('options', arr.map((s: string) => {
                        const [value, ...rest] = s.split('=');
                        return { value: value.trim(), label: (rest.join('=') || value).trim() };
                      }))}
                      placeholder="مثال: approve=تأیید"
                    />
                  </Form.Item>
                )}
                {selected.type === 'calculated' && (
                  <>
                    <Form.Item label="فرمول (پشتیبانی: + - * / % ( ) مقایسه، SUM(items.field)، IF، ROUND)">
                      <Input value={selected.formula} onChange={(e) => patch('formula', e.target.value)} className="mono" placeholder="SUM(items.row_total)" />
                    </Form.Item>
                    <Form.Item label="واحد نمایش">
                      <Select value={selected.moneyUnit} onChange={(v) => patch('moneyUnit', v)} allowClear placeholder="— بدون واحد —">
                        <Option value="ریال">ریال</Option>
                        <Option value="تومان">تومان</Option>
                      </Select>
                    </Form.Item>
                  </>
                )}
                {(selected.type === 'subform' || selected.type === 'subform_single') && (
                  <>
                    <Form.Item label="فرم زیرمجموعه (باید منتشرشده باشد)">
                      <Select value={selected.subformId} onChange={(v) => patch('subformId', v)} allowClear placeholder="انتخاب فرم">
                        {formsList.map((f) => <Option key={f.id} value={f.id}>{f.title}</Option>)}
                      </Select>
                    </Form.Item>
                    {selected.type === 'subform' && (
                      <Row gutter={8}>
                        <Col span={12}><Form.Item label="حداقل ردیف"><InputNumber min={0} style={{ width: '100%' }} value={selected.minRows} onChange={(v) => patch('minRows', v as any)} /></Form.Item></Col>
                        <Col span={12}><Form.Item label="حداکثر ردیف"><InputNumber min={1} style={{ width: '100%' }} value={selected.maxRows} onChange={(v) => patch('maxRows', v as any)} /></Form.Item></Col>
                      </Row>
                    )}
                  </>
                )}
                <Form.Item label="راهنما">
                  <Input value={selected.help} onChange={(e) => patch('help', e.target.value)} />
                </Form.Item>
                <Form.Item label="شرط نمایش (نمونه: request_type == 'goods')">
                  <Input value={selected.visibleIf} onChange={(e) => patch('visibleIf', e.target.value)} className="mono" />
                </Form.Item>
                <Form.Item label="فقط‌خواندنی">
                  <Switch checked={!!selected.readOnly} onChange={(v) => patch('readOnly', v)} />
                </Form.Item>
              </Form>
            )}
          </Card>
        </Col>
      </Row>

      <Modal
        open={previewOpen} onCancel={() => setPreviewOpen(false)} width={860}
        title={`پیش‌نمایش فرم: ${formTitle}`} footer={null}
      >
        <Tabs items={[{
          key: 'desktop', label: 'دسکتاپ',
          children: <FormRenderer schema={schema} hideActions />,
        }, {
          key: 'mobile', label: 'موبایل',
          children: (
            <div style={{ maxWidth: 390, margin: '0 auto', border: '1px solid #e5e7eb', borderRadius: 12, padding: 12 }}>
              <FormRenderer schema={schema} hideActions />
            </div>
          ),
        }, {
          key: 'json', label: 'Schema JSON',
          children: <pre style={{ direction: 'ltr', maxHeight: 480, overflow: 'auto', fontSize: 12 }}>{JSON.stringify(schema, null, 2)}</pre>,
        }]} />
      </Modal>
    </Card>
  );
}
