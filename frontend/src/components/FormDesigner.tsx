// فرم‌ساز — درگ‌اند‌دراپ کامل (پالت→بوم + جابه‌جایی با dnd-kit) + پنل تم و ظاهر + فیلدهای سازمانی
import React, { useMemo, useState } from 'react';
import {
  Button, Card, Col, ColorPicker, Divider, Form, Input, InputNumber, Modal, Popconfirm, Row, Select,
  Slider, Space, Switch, Tabs, Typography, Alert, App as AntApp, Checkbox,
} from 'antd';
import { DeleteOutlined, EyeOutlined, CopyOutlined, BgColorsOutlined, DragOutlined, AppstoreOutlined } from '@ant-design/icons';
import {
  DndContext, DragOverlay, PointerSensor, useSensor, useSensors,
  useDraggable, useDroppable, closestCenter, pointerWithin,
  type CollisionDetection, type DragEndEvent, type DragOverEvent,
} from '@dnd-kit/core';
import {
  SortableContext, arrayMove, useSortable, verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { FormField, FormSchema, FormTheme } from '../lib/formSchema';
import { FIELD_TYPES, THEME_PRESETS, DEFAULT_THEME } from '../lib/formSchema';
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

export interface OrgFieldRow {
  id: number;
  key: string;
  label: string;
  type: string;
  category: string | null;
  config_json: Record<string, unknown> | null;
}

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

// ساخت فیلد از فیلد سازمانی بانک — کلید پایدار + تنظیمات ذخیره‌شده
function newFieldFromOrg(of: OrgFieldRow): FormField {
  const cfg = (of.config_json || {}) as Partial<FormField>;
  const f: FormField = {
    ...cfg,
    key: cfg.key || of.key || `orgf_${of.id}_${Date.now() % 10000}`,
    type: of.type,
    label: of.label,
    colSpan: cfg.colSpan || 8,
  } as FormField;
  if (['select', 'multiselect', 'radio', 'checkgroup'].includes(of.type) && !f.options) {
    f.options = [{ value: 'a', label: 'گزینه الف' }];
  }
  return f;
}

// ---------- آیتم پالت (قابل درگ + کلیک) ----------
function PaletteItem({ id, label, dragData, onAdd, disabled }: {
  id: string; label: string;
  dragData: { source: 'palette' | 'orgfield'; fieldType?: string; orgField?: OrgFieldRow };
  onAdd: () => void; disabled?: boolean;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id,
    data: dragData,
    disabled,
  });
  return (
    <div
      ref={setNodeRef}
      className={`palette-item${isDragging ? ' palette-item--dragging' : ''}${disabled ? ' palette-item--disabled' : ''}`}
      onClick={() => { if (!disabled) onAdd(); }}
      {...attributes} {...listeners}
      title={disabled ? 'برای ویرایش، ابتدا نسخه جدید بسازید' : 'بکشید و روی بوم رها کنید (یا کلیک کنید)'}
    >
      <DragOutlined style={{ fontSize: 10, marginLeft: 4, opacity: 0.5 }} />
      {label}
    </div>
  );
}

// ---------- کارت فیلد روی بوم (قابل مرتب‌سازی) ----------
function SortableField({ field, index, selected, dropBefore, onSelect, onRemove, onCopy }: {
  field: FormField; index: number; selected: boolean; dropBefore: boolean;
  onSelect: () => void; onRemove: () => void; onCopy: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: field.key || `__disp_${index}` });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.45 : 1,
  };
  const isStatic = ['title', 'help', 'divider', 'summary'].includes(field.type);
  return (
    <Col span={field.colSpan || 12} style={style}>
      {dropBefore && <div className="drop-indicator" />}
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

// ---------- ناحیه رهاسازی بوم (باید داخل DndContext رندر شود) ----------
function CanvasDropZone({ children }: { children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: 'canvas' });
  return (
    <div ref={setNodeRef} style={{ minHeight: 120 }} className={isOver ? 'canvas-droptarget' : undefined}>
      {children}
    </div>
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
  const [schema, setSchema] = useState<FormSchema>(initialSchema || { fields: [], theme: DEFAULT_THEME });
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [formsList, setFormsList] = useState<{ id: number; title: string }[]>([]);
  const [orgFields, setOrgFields] = useState<OrgFieldRow[]>([]);
  const [activeLabel, setActiveLabel] = useState<string | null>(null);
  const [dropIndex, setDropIndex] = useState<number | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const isDraft = versionStatus === 'draft';
  const selected: FormField | null = selectedIdx !== null ? schema.fields[selectedIdx] || null : null;
  const theme: FormTheme = schema.theme || DEFAULT_THEME;

  useMemo(() => {
    api.get('/forms').then((r) => setFormsList(r.data.items.filter((f: any) => f.id !== formId))).catch(() => {});
    api.get('/library/fields').then((r) => setOrgFields(r.data.items || [])).catch(() => {});
  }, [formId]);

  const addField = (type: string) => {
    if (!isDraft) { message.warning('فقط نسخه پیش‌نویس قابل ویرایش است؛ ابتدا نسخه جدید بسازید'); return; }
    const f = newField(type);
    setSchema((s) => ({ ...s, fields: [...s.fields, f] }));
    setSelectedIdx(schema.fields.length);
  };

  const addOrgField = (of: OrgFieldRow) => {
    if (!isDraft) { message.warning('فقط نسخه پیش‌نویس قابل ویرایش است؛ ابتدا نسخه جدید بسازید'); return; }
    const f = newFieldFromOrg(of);
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

  const patchTheme = (key: keyof FormTheme, value: unknown) => {
    setSchema((s) => ({ ...s, theme: { ...(s.theme || DEFAULT_THEME), [key]: value } }));
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

  // ---------- درگ‌اند‌دراپ ----------
  // پالت → بوم با pointerWithin (رهاکردن دقیق داخل بوم) + جابه‌جایی با closestCenter
  const collisionDetection: CollisionDetection = (args) => {
    const act = args.active.data.current as { source?: string } | undefined;
    const collisions = act?.source === 'palette' || act?.source === 'orgfield' ? pointerWithin(args) : closestCenter(args);
    return collisions.length ? collisions : closestCenter(args);
  };

  const idOf = (f: FormField, i: number) => f.key || `__disp_${i}`;

  const insertAt = (make: () => FormField, idx: number | null) => {
    setSchema((s) => {
      const f = make();
      const fields = [...s.fields];
      const at = idx === null || idx > fields.length ? fields.length : idx;
      fields.splice(at, 0, f);
      setSelectedIdx(at);
      return { ...s, fields };
    });
  };

  const onDragOver = ({ active, over }: DragOverEvent) => {
    const src = (active.data.current as { source?: string } | undefined)?.source;
    if (!over) { setDropIndex(null); return; }
    if (src === 'palette' || src === 'orgfield') {
      if (over.id === 'canvas') setDropIndex(schema.fields.length);
      else {
        const i = schema.fields.findIndex((f, j) => idOf(f, j) === over.id);
        setDropIndex(i >= 0 ? i : schema.fields.length);
      }
    } else setDropIndex(null);
  };

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    setActiveLabel(null);
    setDropIndex(null);
    if (!over) return;
    const src = (active.data.current as { source?: string; fieldType?: string; orgField?: OrgFieldRow } | undefined);
    // رهاکردن جزء جدید از پالت / فیلد سازمانی روی بوم
    if (src?.source === 'palette') {
      if (over.id === 'canvas' || over.data.current?.sortable) insertAt(() => newField(src.fieldType!), null);
      return;
    }
    if (src?.source === 'orgfield') {
      if (over.id === 'canvas' || over.data.current?.sortable) insertAt(() => newFieldFromOrg(src.orgField!), null);
      return;
    }
    // جابه‌جایی فیلدهای موجود
    if (active.id === over.id) return;
    setSchema((s) => {
      const oldIdx = s.fields.findIndex((f, i) => idOf(f, i) === active.id);
      const newIdx = s.fields.findIndex((f, i) => idOf(f, i) === over.id);
      if (oldIdx < 0 || newIdx < 0) return s;
      return { ...s, fields: arrayMove(s.fields, oldIdx, newIdx) };
    });
  };

  const onDragStart = ({ active }: { active: any }) => {
    const src = active.data.current as { source?: string; fieldType?: string; orgField?: OrgFieldRow } | undefined;
    if (src?.source === 'palette') setActiveLabel(FIELD_TYPES[src.fieldType!]?.label || String(src.fieldType));
    else if (src?.source === 'orgfield') setActiveLabel(`سازمانی: ${src.orgField?.label}`);
    else setActiveLabel(null);
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
      <DndContext
        sensors={sensors}
        collisionDetection={collisionDetection}
        onDragStart={onDragStart}
        onDragOver={onDragOver}
        onDragEnd={onDragEnd}
        onDragCancel={() => { setActiveLabel(null); setDropIndex(null); }}
      >
        <Row gutter={12}>
          {/* پالت — قابل درگ به بوم */}
          <Col span={4}>
            <Card size="small" title={<span><AppstoreOutlined /> اجزا</span>} styles={{ body: { maxHeight: 560, overflow: 'auto' } }}>
              <Alert type="info" style={{ marginBottom: 8, fontSize: 11, padding: '4px 8px' }}
                message="بکشید و روی بوم رها کنید — یا کلیک کنید" />
              {PALETTE_GROUPS.map((g) => (
                <div key={g.group}>
                  <Divider style={{ margin: '8px 0 4px' }}><Text type="secondary" style={{ fontSize: 11 }}>{g.group}</Text></Divider>
                  {g.types.map((t) => (
                    <PaletteItem
                      key={t}
                      id={`palette:${t}`}
                      label={FIELD_TYPES[t].label}
                      dragData={{ source: 'palette', fieldType: t }}
                      onAdd={() => addField(t)}
                      disabled={!isDraft}
                    />
                  ))}
                </div>
              ))}
              {orgFields.length > 0 && (
                <div>
                  <Divider style={{ margin: '8px 0 4px' }}>
                    <Text type="warning" style={{ fontSize: 11 }}>فیلدهای سازمانی (بانک)</Text>
                  </Divider>
                  {orgFields.map((of) => (
                    <PaletteItem
                      key={`org-${of.id}`}
                      id={`orgfield:${of.id}`}
                      label={of.label}
                      dragData={{ source: 'orgfield', orgField: of }}
                      onAdd={() => addOrgField(of)}
                      disabled={!isDraft}
                    />
                  ))}
                </div>
              )}
            </Card>
          </Col>

          {/* بوم — محل رهاسازی */}
          <Col span={13}>
            <Card size="small" title={`بوم طراحی (${schema.fields.length} فیلد)`} styles={{ body: { minHeight: 560, maxHeight: 560, overflow: 'auto', background: '#f8fafc' } }}>
              <CanvasDropZone>
                <SortableContext items={schema.fields.map(idOf)} strategy={verticalListSortingStrategy}>
                  <Row gutter={8}>
                    {schema.fields.map((f, i) => (
                      <SortableField
                        key={idOf(f, i)}
                        field={f} index={i}
                        selected={selectedIdx === i}
                        dropBefore={dropIndex === i}
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
                {!schema.fields.length && (
                  <div className="canvas-empty">
                    جزئی از پالت سمت راست به اینجا بکشید و رها کنید 🖐
                  </div>
                )}
              </CanvasDropZone>
            </Card>
          </Col>

          {/* پنل ویژگی‌ها + تم */}
          <Col span={7}>
            <Card size="small" styles={{ body: { maxHeight: 560, overflow: 'auto' } }}
              title={<span><BgColorsOutlined /> تنظیمات</span>}>
              <Tabs
                size="small"
                items={[
                  {
                    key: 'props', label: 'ویژگی‌های جزء',
                    children: (
                      <>
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
                      </>
                    ),
                  },
                  {
                    key: 'theme', label: 'تم و ظاهر',
                    children: (
                      <div>
                        <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>پیش‌تنم‌های آماده</Typography.Text>
                        <Row gutter={[8, 8]}>
                          {THEME_PRESETS.map((p) => (
                            <Col span={8} key={p.key}>
                              <div
                                className="theme-preset"
                                onClick={() => setSchema((s) => ({ ...s, theme: p.theme }))}
                                title={p.name}
                              >
                                <div className="theme-preset__header" style={{ background: p.theme.headerBg, color: p.theme.headerColor }} />
                                <div className="theme-preset__body" style={{ background: p.theme.background }}>
                                  <div className="theme-preset__line" style={{ background: p.theme.primary }} />
                                  <div className="theme-preset__line theme-preset__line--soft" style={{ background: p.theme.primary, opacity: 0.35 }} />
                                </div>
                                <div style={{ fontSize: 10, padding: '2px 4px', lineHeight: 1.4 }}>{p.name}</div>
                              </div>
                            </Col>
                          ))}
                        </Row>
                        <Divider style={{ margin: '12px 0 8px' }} />
                        <Form layout="vertical" size="small">
                          <Row gutter={8}>
                            <Col span={8}>
                              <Form.Item label="رنگ اصلی">
                                <ColorPicker size="small" value={theme.primary} onChange={(c) => patchTheme('primary', c.toHexString())} showText />
                              </Form.Item>
                            </Col>
                            <Col span={8}>
                              <Form.Item label="پس‌زمینه فیلد">
                                <ColorPicker size="small" value={theme.fieldBg} onChange={(c) => patchTheme('fieldBg', c.toHexString())} showText />
                              </Form.Item>
                            </Col>
                            <Col span={8}>
                              <Form.Item label="رنگ برچسب">
                                <ColorPicker size="small" value={theme.labelColor} onChange={(c) => patchTheme('labelColor', c.toHexString())} showText />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Row gutter={8}>
                            <Col span={12}>
                              <Form.Item label="پس‌زمینه سرصفحه">
                                <ColorPicker size="small" value={theme.headerBg} onChange={(c) => patchTheme('headerBg', c.toHexString())} showText
                                  disabledFormat trigger="click" presets={[{ label: 'گرادیان', colors: THEME_PRESETS.map((p) => p.theme.headerBg || '#fff') }]} />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item label="پس‌زمینه بدنه">
                                <ColorPicker size="small" value={theme.background} onChange={(c) => patchTheme('background', c.toHexString())} showText />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Form.Item label={`گردی گوشه‌ها: ${theme.radius ?? 8}`}>
                            <Slider min={0} max={24} value={theme.radius ?? 8} onChange={(v) => patchTheme('radius', v)} />
                          </Form.Item>
                          <Form.Item label="چیدمان فشرده">
                            <Switch checked={theme.density === 'compact'}
                              onChange={(v) => patchTheme('density', v ? 'compact' : 'comfortable')} />
                          </Form.Item>
                          <Space>
                            <Button size="small" onClick={() => setSchema((s) => ({ ...s, theme: DEFAULT_THEME }))}>بازگشت به پیش‌فرض</Button>
                            <Button size="small" type="primary" onClick={() => setPreviewOpen(true)}>مشاهده زنده تم</Button>
                          </Space>
                        </Form>
                      </div>
                    ),
                  },
                ]}
              />
            </Card>
          </Col>
        </Row>

        {/* پیش‌نمایش شناور هنگام درگ */}
        <DragOverlay dropAnimation={null}>
          {activeLabel && <div className="drag-overlay-chip"><DragOutlined /> {activeLabel}</div>}
        </DragOverlay>

        <Modal
          open={previewOpen} onCancel={() => setPreviewOpen(false)} width={860}
          title={`پیش‌نمایش فرم: ${formTitle}`} footer={null}
        >
          <Tabs items={[{
            key: 'desktop', label: 'دسکتاپ',
            children: <FormRenderer schema={schema} hideActions showHeader />,
          }, {
            key: 'mobile', label: 'موبایل',
            children: (
              <div style={{ maxWidth: 390, margin: '0 auto', border: '1px solid #e5e7eb', borderRadius: 12, padding: 12 }}>
                <FormRenderer schema={schema} hideActions showHeader />
              </div>
            ),
          }, {
            key: 'json', label: 'Schema JSON',
            children: <pre style={{ direction: 'ltr', maxHeight: 480, overflow: 'auto', fontSize: 12 }}>{JSON.stringify(schema, null, 2)}</pre>,
          }]} />
        </Modal>
      </DndContext>
    </Card>
  );
}
