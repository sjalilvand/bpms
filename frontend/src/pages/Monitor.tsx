// پایش فرایندها — همه نمونه‌ها با فیلتر (ناظر/مدیر)
import { useCallback, useEffect, useState } from 'react';
import { Button, Card, Input, Select, Space, Statistic, Table, Tag, App as AntApp, Col, Row } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { api, InstanceRow, Paged, ProcessRow, extractError } from '../api/client';

const STATUS: Record<string, { color: string; text: string }> = {
  running: { color: 'processing', text: 'در جریان' },
  completed: { color: 'success', text: 'تکمیل‌شده' },
  cancelled: { color: 'default', text: 'لغوشده' },
  error: { color: 'error', text: 'خطادار' },
};

export default function Monitor() {
  const nav = useNavigate();
  const { message } = AntApp.useApp();
  const [rows, setRows] = useState<InstanceRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [definitionId, setDefinitionId] = useState<number | undefined>();
  const [processes, setProcesses] = useState<ProcessRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [counts, setCounts] = useState<Record<string, number>>({ running: 0, completed: 0 });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get<Paged<InstanceRow>>('/process-instances', {
        params: { page, page_size: 12, status, definition_id: definitionId },
      });
      setRows(r.data.items);
      setTotal(r.data.total);
    } catch (e) { message.error(extractError(e)); }
    finally { setLoading(false); }
  }, [page, status, definitionId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get('/processes').then((r) => setProcesses(r.data.items)).catch(() => {});
    api.get('/process-instances', { params: { status: 'running', page_size: 1 } }).then((r) => setCounts((c) => ({ ...c, running: r.data.total }))).catch(() => {});
    api.get('/process-instances', { params: { status: 'completed', page_size: 1 } }).then((r) => setCounts((c) => ({ ...c, completed: r.data.total }))).catch(() => {});
  }, []);

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="نمونه‌های در جریان" value={counts.running} /></Card></Col>
        <Col span={6}><Card><Statistic title="تکمیل‌شده" value={counts.completed} /></Card></Col>
        <Col span={6}><Card><Statistic title="مجموع نمونه‌ها" value={total} /></Card></Col>
        <Col span={6}>
          <Card size="small" style={{ height: '100%', display: 'flex', alignItems: 'center' }}>
            <Button block onClick={async () => {
              try { const r = await api.post('/engine/tick'); message.success(`تایمرها بررسی شد (${r.data.touched} نمونه به‌روزرسانی شد)`); }
              catch (e) { message.error(extractError(e)); }
            }}>بررسی تایمرهای منتظر</Button>
          </Card>
        </Col>
      </Row>
      <Card
        title="پایش نمونه‌های اجرایی"
        extra={
          <Space wrap>
            <Select placeholder="فرایند" allowClear style={{ width: 200 }} value={definitionId}
              onChange={(v) => { setDefinitionId(v); setPage(1); }}
              options={processes.map((p) => ({ value: p.id, label: p.title }))} />
            <Select placeholder="وضعیت" allowClear style={{ width: 140 }} value={status || undefined}
              onChange={(v) => { setStatus(v || ''); setPage(1); }}
              options={Object.entries(STATUS).map(([k, v]) => ({ value: k, label: v.text }))} />
            <Button icon={<ReloadOutlined />} onClick={load} />
          </Space>
        }
      >
        <Table
          rowKey="id" size="small" loading={loading} dataSource={rows}
          pagination={{ current: page, pageSize: 12, total, onChange: setPage, showTotal: (t) => `مجموع: ${t}` }}
          onRow={(r) => ({ onClick: () => nav(`/instances/${r.id}`), style: { cursor: 'pointer' } })}
          columns={[
            { title: 'شناسه', dataIndex: 'id', width: 80, render: (v: number) => `#${v}` },
            { title: 'عنوان', dataIndex: 'title' },
            { title: 'فرایند', key: 'p', render: (_: unknown, r: InstanceRow) => r.process?.title },
            { title: 'وضعیت', dataIndex: 'status', render: (s: string) => <Tag color={STATUS[s]?.color}>{STATUS[s]?.text || s}</Tag> },
            { title: 'وظایف باز', dataIndex: 'open_tasks', width: 90 },
            { title: 'شروع', dataIndex: 'started_at_jalali' },
          ]}
        />
      </Card>
    </div>
  );
}
