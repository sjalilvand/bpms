// ممیزی — سوابق رویدادهای سامانه (فقط مشاهده)
import { useCallback, useEffect, useState } from 'react';
import { Button, Card, Input, Space, Table, Tag, App as AntApp } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { api, Paged, extractError } from '../api/client';
import { gregorianToJalaliStr } from '../lib/persian';

interface AuditRow {
  id: number; user_id: number | null; action: string; entity: string | null;
  entity_id: number | null; detail: Record<string, unknown> | null; ip: string | null; created_at: string | null;
}

export default function AuditPage() {
  const { message } = AntApp.useApp();
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [action, setAction] = useState('');
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get<Paged<AuditRow>>('/audit', { params: { page, page_size: 15, action } });
      setRows(r.data.items);
      setTotal(r.data.total);
    } catch (e) { message.error(extractError(e)); }
    finally { setLoading(false); }
  }, [page, action]);

  useEffect(() => { load(); }, [load]);

  return (
    <Card
      title="سوابق ممیزی (فقط مشاهده)"
      extra={<Space>
        <Input.Search placeholder="فیلتر عملیات (مثال: task.)" allowClear onSearch={(v) => { setAction(v); setPage(1); }} style={{ width: 240 }} />
        <Space.Compact><Button icon={<ReloadOutlined />} onClick={load} /></Space.Compact>
      </Space>}
    >
      <Table
        rowKey="id" size="small" loading={loading} dataSource={rows}
        pagination={{ current: page, pageSize: 15, total, onChange: setPage, showTotal: (t) => `مجموع: ${t}` }}
        columns={[
          { title: 'زمان', key: 'time', width: 160, render: (_: unknown, r: AuditRow) => gregorianToJalaliStr(r.created_at, true) },
          { title: 'کاربر', dataIndex: 'user_id', width: 80, render: (v: number | null) => v ? `#${v}` : 'سیستم' },
          { title: 'عملیات', dataIndex: 'action', render: (v: string) => <Tag>{v}</Tag> },
          { title: 'موجودیت', key: 'ent', render: (_: unknown, r: AuditRow) => r.entity ? `${r.entity} #${r.entity_id}` : '—' },
          { title: 'جزئیات', dataIndex: 'detail', ellipsis: true, render: (v: Record<string, unknown> | null) => v && Object.keys(v).length ? JSON.stringify(v) : '—' },
          { title: 'IP', dataIndex: 'ip', width: 120, render: (v: string | null) => v || '—' },
        ]}
      />
    </Card>
  );
}
