// فاز ۴ — شرط‌ساز بصری: ویرایشگر ساختار شرط (فیلد/عملگر/مقدار با ترکیب و/یا)
import React from 'react';
import { AutoComplete, Button, Input, Popconfirm, Segmented, Select, Space, Switch, Tooltip, Typography } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { CondCompare, CondGroup, CondOp, OP_LABELS, OPS_WITH_VALUE, coerceValue } from '../lib/conditions';

const MAX_DEPTH = 3;

interface Props {
  value: CondGroup | null;
  onChange: (g: CondGroup) => void;
  varOptions?: string[];
  depth?: number;
}

function FieldSelect({ value, onChange, varOptions }: { value: string; onChange: (v: string) => void; varOptions?: string[] }) {
  const opts = (varOptions || []).map((v) => ({ value: v, label: v }));
  return (
    <AutoComplete
      style={{ minWidth: 150, flex: 2 }}
      value={value}
      onChange={onChange}
      options={opts}
      filterOption={(input, option) => String(option?.value || '').toLowerCase().includes(input.toLowerCase())}
      placeholder="نام متغیر / فیلد"
    />
  );
}

function ValueInput({ op, value, onChange }: { op: CondOp; value: unknown; onChange: (v: unknown) => void }) {
  if (op === 'empty' || op === 'not_empty') return <span style={{ color: '#94a3b8', fontSize: 12 }}>—</span>;
  if (op === 'in' || op === 'not_in') {
    const list = Array.isArray(value) ? value : [];
    return (
      <Select
        mode="tags" open={false} tokenSeparators={[',']} style={{ minWidth: 190, flex: 3 }}
        value={list.map((v) => String(v))}
        onChange={(arr) => onChange(arr.map((s) => coerceValue(s)))}
        placeholder="مقادیر را با کاما جدا کنید"
      />
    );
  }
  return (
    <Input
      style={{ flex: 3, minWidth: 150 }} value={value === null || value === undefined ? '' : String(value)}
      onChange={(e) => onChange(coerceValue(e.target.value))}
      placeholder="مقدار (عدد، متن، true/false)"
    />
  );
}

function CompareRow({ item, onChange, onRemove, varOptions }: {
  item: CondCompare; onChange: (c: CondCompare) => void; onRemove: () => void; varOptions?: string[];
}) {
  return (
    <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
      {item.negate && (
        <Tooltip title="این شرط نفی (not) دارد — برای حذف کلیک کنید">
          <TagNot onOff={() => onChange({ ...item, negate: false })} />
        </Tooltip>
      )}
      <FieldSelect value={item.field} onChange={(v) => onChange({ ...item, field: v })} varOptions={varOptions} />
      <Select<CondOp>
        style={{ minWidth: 140, flex: 2 }} value={item.op}
        onChange={(v) => onChange({ ...item, op: v, value: v === 'empty' || v === 'not_empty' ? undefined : item.value })}
        options={(Object.keys(OP_LABELS) as CondOp[]).map((o) => ({ value: o, label: OP_LABELS[o] }))}
      />
      <ValueInput op={item.op} value={item.value} onChange={(v) => onChange({ ...item, value: v })} />
      <Space size={2}>
        <Tooltip title="نفی شرط (not)">
          <Switch size="small" checked={!!item.negate} onChange={(v) => onChange({ ...item, negate: v })} />
        </Tooltip>
        <Popconfirm title="حذف این شرط؟" onConfirm={onRemove} okText="حذف" cancelText="انصراف">
          <Button size="small" type="text" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      </Space>
    </div>
  );
}

function TagNot({ onOff }: { onOff: () => void }) {
  return (
    <Typography.Text code onClick={onOff} style={{ cursor: 'pointer', color: '#d4380d' }}>NOT</Typography.Text>
  );
}

export default function ConditionBuilder({ value, onChange, varOptions, depth = 1 }: Props) {
  if (!value) return null;
  const group = value;
  const update = (items: (CondCompare | CondGroup)[]) => onChange({ ...group, items });

  return (
    <div data-testid="condition-builder" style={{ border: '1px dashed #cbd5e1', borderRadius: 8, padding: 10, background: '#f8fafc' }}>
      {(group.items || []).map((it, idx) => {
        const isGroup = !!(it as CondGroup).items;
        return (
          <div key={idx} data-testid={`cond-row-${idx}`}>
            <CompareRow
              item={it as CondCompare}
              varOptions={varOptions}
              onChange={(c) => { const items = [...group.items]; items[idx] = c; update(items); }}
              onRemove={() => update(group.items.filter((_, i) => i !== idx))}
            />
            {idx < (group.items || []).length - 1 && (
              <div style={{ display: 'flex', justifyContent: 'center', margin: '2px 0 6px' }}>
                <Segmented
                  size="small"
                  value={group.combinator}
                  onChange={(v) => onChange({ ...group, combinator: v as 'and' | 'or' })}
                  options={[
                    { value: 'and', label: 'و (AND)' },
                    { value: 'or', label: 'یا (OR)' },
                  ]}
                />
              </div>
            )}
            {isGroup && (
              <div style={{ paddingRight: 14, margin: '0 0 6px', borderRight: '2px solid #94a3b8' }}>
                <ConditionBuilder
                  value={it as CondGroup}
                  varOptions={varOptions}
                  depth={depth + 1}
                  onChange={(g) => { const items = [...group.items]; items[idx] = g; update(items); }}
                />
              </div>
            )}
          </div>
        );
      })}
      <Space size={6} wrap>
        <Button
          size="small" icon={<PlusOutlined />} disabled={(group.items || []).length >= 20}
          onClick={() => update([...group.items, { kind: 'compare', field: '', op: 'eq', value: '' }])}
        >
          افزودن شرط
        </Button>
        {depth < MAX_DEPTH && (
          <Button
            size="small" icon={<PlusOutlined />} disabled={(group.items || []).length >= 20}
            onClick={() => update([...group.items, { kind: 'group', combinator: 'and', items: [{ kind: 'compare', field: '', op: 'eq', value: '' }] }])}
          >
            افزودن گروه (پرانتز)
          </Button>
        )}
      </Space>
    </div>
  );
}
