// درخواست‌های من — فهرست و مشاهده وضعیت
import { useCallback, useEffect, useState } from 'react';
import { Button, Card, Input, Select, Space, Table, Tag, App as AntApp } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { api, InstanceRow, Paged, extractError } from '../api/client';

const STATUS: Record<string, { color: string; text: string }> = {
  running: { color: 'processing', text: 'در جریان' },
  completed: { color: 'success', text: 'تکمیل‌شده' },
  cancelled: { color: 'default', text: 'لغوشده' },
  error: { color: 'error', text: 'خطادار' },
};

export default function MyRequests() {
  const nav = useNavigate();
  const { message } = AntApp.useApp();
  const [rows, setRows] = useState<InstanceRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get<Paged<InstanceRow>>('/process-instances', {
        params: { scope: 'mine', page, page_size: 10, status, q },
      });
      setRows(r.data.items);
      setTotal(r.data.total);
    } catch (e) { message.error(extractError(e)); }
    finally { setLoading(false); }
  }, [page, status, q]);

  useEffect(() => { load(); }, [load]);

  return (
    <Card
      title="درخواست‌های من"
      extra={
        <Space wrap>
          <Select placeholder="وضعیت" allowClear style={{ width: 140 }} value={status || undefined}
            onChange={(v) => { setStatus(v || ''); setPage(1); }}
            options={Object.entries(STATUS).map(([k, v]) => ({ value: k, label: v.text }))} />
          <Input.Search placeholder="جست‌وجوی عنوان/شماره" allowClear style={{ width: 220 }}
            onSearch={(v) => { setQ(v); setPage(1); }} />
          <Button icon={<ReloadOutlined />} onClick={load} />
        </Space>
      }
    >
      <Table
        rowKey="id" size="small" loading={loading}
        dataSource={rows}
        pagination={{ current: page, pageSize: 10, total, onChange: setPage, showTotal: (t) => `مجموع: ${t}` }}
        onRow={(r) => ({ onClick: () => nav(`/instances/${r.id}`), style: { cursor: 'pointer' } })}
        columns={[
          { title: 'شناسه', dataIndex: 'id', width: 80, render: (v: number) => `#${v}` },
          { title: 'عنوان', dataIndex: 'title' },
          { title: 'فرایند', key: 'p', render: (_: unknown, r: InstanceRow) => r.process?.title },
          { title: 'نسخه', dataIndex: 'version', width: 70 },
          { title: 'وضعیت', dataIndex: 'status', render: (s: string) => <Tag color={STATUS[s]?.color}>{STATUS[s]?.text || s}</Tag> },
          { title: 'شروع', dataIndex: 'started_at_jalali' },
        ]}
      />
    </Card>
  );
}
