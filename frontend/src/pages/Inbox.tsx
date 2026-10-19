// کارتابل — وظایف من / صف گروهی (با Claim) / انجام‌شده‌ها
import { useCallback, useEffect, useState } from 'react';
import {
  Button, Card, Drawer, Modal, Space, Table, Tabs, Tag, Typography, App as AntApp, Input,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import { api, TaskRow, Paged, extractError } from '../api/client';
import FormRenderer from '../components/FormRenderer';
import type { FormSchema } from '../lib/formSchema';
import { gregorianToJalaliStr } from '../lib/persian';
import { useAuth } from '../auth/AuthContext';

const STATUS_TAG: Record<string, { color: string; text: string }> = {
  ready: { color: 'processing', text: 'آماده' },
  claimed: { color: 'warning', text: 'دریافت‌شده' },
  completed: { color: 'success', text: 'انجام‌شده' },
  cancelled: { color: 'default', text: 'لغو‌شده' },
};

export default function Inbox() {
  const { message, modal } = AntApp.useApp();
  const { user } = useAuth();
  const [sp, setSp] = useSearchParams();
  const [tab, setTab] = useState(sp.get('tab') || 'mine');
  const [rows, setRows] = useState<TaskRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(false);
  const [current, setCurrent] = useState<TaskRow | null>(null);
  const [schema, setSchema] = useState<FormSchema | null>(null);
  const [instanceData, setInstanceData] = useState<Record<string, unknown>>({});
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const endpoint = tab === 'group' ? '/tasks/group' : tab === 'done' ? '/tasks/completed' : '/tasks/inbox';
      const r = await api.get<Paged<TaskRow>>(endpoint, { params: { page, page_size: 10, q } });
      setRows(r.data.items);
      setTotal(r.data.total);
    } catch (e) { message.error(extractError(e)); }
    finally { setLoading(false); }
  }, [tab, page, q]);

  useEffect(() => { load(); }, [load]);

  // به‌روزرسانی زنده کارتابل از رویدادهای SSE (فاز ۳)
  useEffect(() => {
    const onRefresh = () => { load(); };
    window.addEventListener('bpms:inbox-refresh', onRefresh);
    return () => window.removeEventListener('bpms:inbox-refresh', onRefresh);
  }, [load]);

  // باز کردن مستقیم وظیفه از لینک اعلان
  useEffect(() => {
    const tid = sp.get('task');
    if (tid) {
      api.get(`/tasks/${tid}`).then((r) => openTask(r.data)).catch((e) => message.error(extractError(e)));
    }
  }, [sp]);

  const [results, setResults] = useState<{ value: string; label: string }[] | undefined>(undefined);

  const openTask = async (t: TaskRow) => {
    setCurrent(t);
    setSchema(null);
    setInstanceData({});
    setResults(undefined);
    if (t.form_version_id) {
      try {
        const r = await api.get(`/forms/versions/${t.form_version_id}`);
        setSchema(r.data.schema_json);
      } catch { setSchema(null); }
    }
    // داده فعلی موتور برای نمایش مراحل قبلی
    try {
      const r = await api.get(`/tasks/${t.id}/data`);
      setInstanceData(r.data.data || {});
    } catch { /* ignore */ }
    // دکمه‌های نتیجه از اتصال فعالیت
    try {
      const inst = await api.get(`/process-instances/${t.instance_id}`);
      const vid = inst.data.version_id;
      const ver = await api.get(`/processes/versions/${vid}`);
      const b = (ver.data.config_json?.bindings || {})[t.spec_id];
      if (b?.results?.length) setResults(b.results);
    } catch { /* ignore */ }
  };

  const claim = async (t: TaskRow) => {
    try {
      await api.post(`/tasks/${t.id}/claim`);
      message.success('وظیفه دریافت شد');
      load();
    } catch (e) { message.error(extractError(e)); }
  };

  const release = async (t: TaskRow) => {
    try {
      await api.post(`/tasks/${t.id}/release`);
      message.success('وظیفه آزاد شد');
      load();
    } catch (e) { message.error(extractError(e)); }
  };

  const complete = async (values: Record<string, unknown>, result?: string) => {
    if (!current) return;
    setSubmitting(true);
    try {
      await api.post(`/tasks/${current.id}/complete`, { data: values, result, comment: values?.comment || '' });
      message.success('وظیفه با موفقیت تکمیل شد');
      setCurrent(null);
      load();
    } catch (e) {
      message.error({ content: extractError(e), duration: 6 });
    } finally { setSubmitting(false); }
  };

  const showMyRole = (t: TaskRow) => {
    const mine = t.assignee_id === user?.id;
    const claimedByMe = t.claimed_by_id === user?.id;
    if (t.status === 'ready' && t.candidate_role) return <Button size="small" type="primary" onClick={() => claim(t)}>دریافت</Button>;
    if (t.status === 'ready' && mine) return <Button size="small" type="primary" onClick={() => openTask(t)}>انجام</Button>;
    if (t.status === 'claimed' && claimedByMe) return <Space><Button size="small" type="primary" onClick={() => openTask(t)}>انجام</Button><Button size="small" onClick={() => release(t)}>آزادسازی</Button></Space>;
    return <Tag>{STATUS_TAG[t.status]?.text || t.status}</Tag>;
  };

  const columns = [
    { title: 'وظیفه', dataIndex: 'name', key: 'name' },
    { title: 'فرایند', key: 'process', render: (_: unknown, t: TaskRow) => t.instance?.process_title },
    { title: 'نمونه', key: 'inst', render: (_: unknown, t: TaskRow) => <a onClick={() => window.open(`/instances/${t.instance_id}`, '_self')}>#{t.instance_id}</a> },
    { title: 'وضعیت', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={STATUS_TAG[s]?.color}>{STATUS_TAG[s]?.text || s}</Tag> },
    { title: 'موعد', dataIndex: 'due_at', key: 'due_at', render: (v: string) => v ? gregorianToJalaliStr(v, true) || '-' : '—' },
    { title: 'تاریخ ایجاد', dataIndex: 'created_at_jalali', key: 'created_at_jalali' },
    {
      title: 'عملیات', key: 'act',
      render: (_: unknown, t: TaskRow) => showMyRole(t),
    },
  ];

  return (
    <Card
      title="کارتابل"
      extra={<Space><Input.Search placeholder="جست‌وجوی وظیفه" allowClear onSearch={(v) => { setQ(v); setPage(1); }} style={{ width: 220 }} /><Button icon={<ReloadOutlined />} onClick={load} /></Space>}
    >
      <Tabs
        activeKey={tab}
        onChange={(k) => { setTab(k); setPage(1); setSp({}); }}
        items={[
          { key: 'mine', label: 'وظایف من' },
          { key: 'group', label: 'صف گروهی' },
          { key: 'done', label: 'انجام‌شده‌ها' },
        ]}
      />
      <Table
        rowKey="id" size="small" loading={loading}
        columns={columns} dataSource={rows}
        pagination={{ current: page, pageSize: 10, total, onChange: setPage, showTotal: (t) => `مجموع: ${t}` }}
      />

      <Drawer
        open={!!current} onClose={() => setCurrent(null)} width={720}
        title={current ? `${current.name} — نمونه #${current.instance_id}` : ''}
        destroyOnClose
      >
        {current && (
          <div>
            <Typography.Paragraph type="secondary">
              فرایند: {current.instance?.process_title} • وضعیت نمونه: {current.instance?.status}
            </Typography.Paragraph>
            {current.form_version_id ? (
              schema ? (
                <FormRenderer
                  schema={schema}
                  initialValues={instanceData}
                  submitting={submitting}
                  submitResults={results}
                  onFinish={complete}
                />
              ) : (
                <div>
                  <Typography.Text type="warning">این فعالیت فرم متصل ندارد.</Typography.Text>
                  <Button type="primary" style={{ marginTop: 12 }} loading={submitting}
                    onClick={() => complete({})}>تکمیل بدون فرم</Button>
                </div>
              )
            ) : (
              <div>
                <Typography.Text type="warning">این فعالیت فرم متصل ندارد.</Typography.Text>
                <Button type="primary" style={{ marginTop: 12 }} loading={submitting}
                  onClick={() => complete({})}>تکمیل بدون فرم</Button>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </Card>
  );
}
