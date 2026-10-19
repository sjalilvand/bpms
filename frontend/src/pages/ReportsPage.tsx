// گزارش‌ساز و KPI — فاز ۶
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button, Card, Col, Empty, Input, Modal, Row, Select, Space, Spin, Statistic,
  Table, Tabs, Tag, Typography, App,
} from 'antd';
import {
  BarChartOutlined, ClockCircleOutlined, DeleteOutlined, ExclamationCircleOutlined,
  ReloadOutlined, SaveOutlined, RiseOutlined, TeamOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import { api, extractError } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { gregorianToJalaliStr } from '../lib/persian';

interface Overview {
  period: { from: string; to: string };
  instances: {
    total: number; by_status: Record<string, number>;
    completion_rate: number; avg_per_day: number;
  };
  cycle_time_seconds: { avg: number; min: number; max: number; p50: number; p95: number; completed_count: number };
  tasks: { total: number; ready: number; claimed: number; completed: number; overdue_active: number; avg_wait_seconds: number; avg_handling_seconds: number };
  sla: { warned: number; escalated: number; breach_rate: number };
}

interface BottleneckRow {
  spec_id: string; name: string; created: number; completed: number; pending: number;
  avg_wait_seconds: number; avg_handling_seconds: number; max_handling_seconds: number;
  p95_handling_seconds: number; overdue_active: number; sla_escalated: number;
}

interface WorkloadRow {
  kind: 'user' | 'role'; ref: number | string; name: string | null; label: string;
  completed: number; active: number; overdue_active: number; sla_escalated: number;
  avg_handling_seconds: number;
}

interface VolumeRow { date: string; started: number; completed: number }

interface SavedReportRow {
  id: number; name: string; description: string; dataset: string;
  filters: Record<string, unknown>; created_by_id: number | null;
}

interface ProcessOption { id: number; key: string; title: string }

const DATASET_TITLES: Record<string, string> = {
  overview: 'شاخص‌های کلی',
  bottlenecks: 'گلوگاه‌ها',
  workload: 'بار کاری',
  volume: 'حجم روزانه',
};

function fmtDuration(sec: number | null | undefined): string {
  if (sec === null || sec === undefined || Number.isNaN(sec)) return '—';
  if (sec === 0) return '۰';
  if (sec < 60) return `${Math.round(sec)} ثانیه`;
  if (sec < 3600) return `${(sec / 60).toFixed(1)} دقیقه`;
  if (sec < 86400) return `${(sec / 3600).toFixed(1)} ساعت`;
  return `${(sec / 86400).toFixed(1)} روز`;
}

// نمودار میله‌ای افقی سبک (بدون وابستگی جدید)
function MiniBars({ rows }: { rows: VolumeRow[] }) {
  const max = Math.max(1, ...rows.map((r) => Math.max(r.started, r.completed)));
  const shown = rows.slice(-30);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {shown.map((r) => (
        <div key={r.date} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
          <span style={{ width: 88, color: '#6b7280', whiteSpace: 'nowrap' }}>
            {gregorianToJalaliStr(r.date) || r.date}
          </span>
          <div style={{ flex: 1 }}>
            <div style={{ height: 8, borderRadius: 4, background: '#e5e7eb', position: 'relative' }}>
              <div style={{
                height: 8, borderRadius: 4, width: `${(r.started / max) * 100}%`,
                background: '#3b82f6', position: 'absolute', insetInlineStart: 0,
              }} />
            </div>
            <div style={{ height: 8, borderRadius: 4, background: '#e5e7eb', marginTop: 2, position: 'relative' }}>
              <div style={{
                height: 8, borderRadius: 4, width: `${(r.completed / max) * 100}%`,
                background: '#10b981', position: 'absolute', insetInlineStart: 0,
              }} />
            </div>
          </div>
          <span style={{ width: 56, textAlign: 'left', direction: 'ltr' }}>
            {r.started}/{r.completed}
          </span>
        </div>
      ))}
      {shown.length === 0 && <Empty description="داده‌ای در این بازه نیست" />}
      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
        <Tag color="blue" style={{ marginInlineEnd: 4 }}>شروع‌شده</Tag>
        <Tag color="green">تکمیل‌شده</Tag> (شروع/تکمیل هر روز)
      </div>
    </div>
  );
}

export default function ReportsPage() {
  const { user } = useAuth();
  const { message } = App.useApp();
  const canManage = !!user?.is_superadmin || user?.roles.some((r) => r.permissions?.includes('report.manage'));

  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(30);
  const [definitionId, setDefinitionId] = useState<number | undefined>();
  const [status, setStatus] = useState<string | undefined>();
  const [processes, setProcesses] = useState<ProcessOption[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [bottlenecks, setBottlenecks] = useState<BottleneckRow[]>([]);
  const [workload, setWorkload] = useState<WorkloadRow[]>([]);
  const [volume, setVolume] = useState<VolumeRow[]>([]);
  const [saved, setSaved] = useState<SavedReportRow[]>([]);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [saveDesc, setSaveDesc] = useState('');
  const [saveDataset, setSaveDataset] = useState('overview');

  const filters = useMemo(() => {
    const f: Record<string, unknown> = { days };
    if (definitionId) f.definition_id = definitionId;
    if (status) f.status = status;
    return f;
  }, [days, definitionId, status]);

  const params = useMemo(() => {
    const p: Record<string, unknown> = { days };
    if (definitionId) p.definition_id = definitionId;
    if (status) p.status = status;
    return p;
  }, [days, definitionId, status]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [ov, bo, wl, vo] = await Promise.all([
        api.get('/reports/kpi/overview', { params }),
        api.get('/reports/kpi/bottlenecks', { params }),
        api.get('/reports/kpi/workload', { params }),
        api.get('/reports/kpi/volume', { params }),
      ]);
      setOverview(ov.data as Overview);
      setBottlenecks(bo.data.items as BottleneckRow[]);
      setWorkload(wl.data.items as WorkloadRow[]);
      setVolume(vo.data.items as VolumeRow[]);
    } catch (e) {
      message.error(extractError(e));
    } finally {
      setLoading(false);
    }
  }, [params, message]);

  const loadSaved = useCallback(() => {
    api.get('/reports/saved').then((r) => setSaved(r.data.items as SavedReportRow[])).catch(() => {});
  }, []);

  useEffect(() => {
    api.get('/reports/options').then((r) => setProcesses(r.data.processes as ProcessOption[])).catch(() => {});
    loadSaved();
  }, [loadSaved]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const saveCurrent = async () => {
    if (!saveName.trim()) { message.warning('نام گزارش را وارد کنید'); return; }
    try {
      await api.post('/reports/saved', {
        name: saveName.trim(), description: saveDesc, dataset: saveDataset, filters,
      });
      message.success('گزارش ذخیره شد');
      setSaveOpen(false); setSaveName(''); setSaveDesc('');
      loadSaved();
    } catch (e) { message.error(extractError(e)); }
  };

  const runSaved = async (r: SavedReportRow) => {
    try {
      const resp = await api.get(`/reports/saved/${r.id}/run`);
      const d = resp.data.data;
      if (r.dataset === 'overview') {
        message.info(`مجموع نمونه‌ها: ${d.instances.total} — نرخ تکمیل: ${d.instances.completion_rate}٪ — میانگین چرخه: ${fmtDuration(d.cycle_time_seconds.avg)}`);
      } else {
        message.info(`${DATASET_TITLES[r.dataset] || r.dataset}: ${d.items.length} ردیف — جزئیات در کنسول مرورگر`);
        // برای جزئیات: بارگذاری مجدد با فیلترهای گزارش
        if (typeof d.items[0]?.spec_id !== 'undefined') setBottlenecks(d.items as BottleneckRow[]);
        else setWorkload(d.items as WorkloadRow[]);
      }
    } catch (e) { message.error(extractError(e)); }
  };

  const deleteSaved = (r: SavedReportRow) => {
    Modal.confirm({
      title: `حذف گزارش «${r.name}»؟`,
      icon: <ExclamationCircleOutlined />,
      content: 'این عملیات بازگشت‌پذیر نیست.',
      okText: 'حذف', okType: 'danger', cancelText: 'انصراف',
      onOk: async () => {
        try {
          await api.delete(`/reports/saved/${r.id}`);
          message.success('حذف شد');
          loadSaved();
        } catch (e) { message.error(extractError(e)); }
      },
    });
  };

  const statusLabel: Record<string, string> = {
    running: 'در جریان', completed: 'تکمیل‌شده', cancelled: 'لغوشده', error: 'خطا',
  };

  const bottleneckCols = [
    { title: 'گام فرایند', dataIndex: 'name', key: 'name', render: (v: string, r: BottleneckRow) => (
      <Space direction="vertical" size={0}>
        <Typography.Text strong>{v}</Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 11, direction: 'ltr' }}>{r.spec_id}</Typography.Text>
      </Space>
    ) },
    { title: 'ایجاد', dataIndex: 'created', key: 'created', align: 'center' as const },
    { title: 'تکمیل', dataIndex: 'completed', key: 'completed', align: 'center' as const },
    { title: 'در انتظار', dataIndex: 'pending', key: 'pending', align: 'center' as const,
      render: (v: number) => v > 0 ? <Tag color="orange">{v}</Tag> : <Tag>۰</Tag> },
    { title: 'میانگین انتظار', dataIndex: 'avg_wait_seconds', key: 'wait', render: fmtDuration },
    { title: 'میانگین رسیدگی', dataIndex: 'avg_handling_seconds', key: 'handle',
      render: (v: number) => <Typography.Text strong>{fmtDuration(v)}</Typography.Text> },
    { title: 'بیشترین', dataIndex: 'max_handling_seconds', key: 'max', render: fmtDuration },
    { title: 'صدک ۹۵', dataIndex: 'p95_handling_seconds', key: 'p95', render: fmtDuration },
    { title: 'سرریز SLA', dataIndex: 'sla_escalated', key: 'sla', align: 'center' as const,
      render: (v: number) => v > 0 ? <Tag color="red">{v}</Tag> : '—' },
  ];

  const workloadCols = [
    { title: 'کاربر / صف', dataIndex: 'label', key: 'label',
      render: (v: string, r: WorkloadRow) => r.kind === 'role'
        ? <Tag icon={<TeamOutlined />} color="purple">{v}</Tag>
        : <Typography.Text strong>{v}</Typography.Text> },
    { title: 'تکمیل‌شده', dataIndex: 'completed', key: 'completed', align: 'center' as const },
    { title: 'فعال (بار جاری)', dataIndex: 'active', key: 'active', align: 'center' as const },
    { title: 'سرریز فعال', dataIndex: 'overdue_active', key: 'overdue', align: 'center' as const,
      render: (v: number) => v > 0 ? <Tag color="red">{v}</Tag> : '—' },
    { title: 'فرازدگی SLA', dataIndex: 'sla_escalated', key: 'esc', align: 'center' as const,
      render: (v: number) => v > 0 ? <Tag color="volcano">{v}</Tag> : '—' },
    { title: 'میانگین رسیدگی', dataIndex: 'avg_handling_seconds', key: 'handle', render: fmtDuration },
  ];

  const savedCols = [
    { title: 'نام', dataIndex: 'name', key: 'name', render: (v: string, r: SavedReportRow) => (
      <Space direction="vertical" size={0}>
        <Typography.Text strong>{v}</Typography.Text>
        {r.description && <Typography.Text type="secondary" style={{ fontSize: 12 }}>{r.description}</Typography.Text>}
      </Space>
    ) },
    { title: 'نوع', dataIndex: 'dataset', key: 'dataset', render: (v: string) => <Tag color="geekblue">{DATASET_TITLES[v] || v}</Tag> },
    { title: 'عملیات', key: 'actions', align: 'center' as const, render: (_: unknown, r: SavedReportRow) => (
      <Space>
        <Button size="small" icon={<BarChartOutlined />} onClick={() => runSaved(r)}>اجرا</Button>
        {canManage && <Button size="small" danger icon={<DeleteOutlined />} onClick={() => deleteSaved(r)}>حذف</Button>}
      </Space>
    ) },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>گزارش‌ساز و شاخص‌های کلیدی (KPI)</Typography.Title>
        <Space wrap>
          <Select
            style={{ minWidth: 180 }} placeholder="همه فرایندها" allowClear
            value={definitionId} onChange={(v) => setDefinitionId(v)}
            options={processes.map((p) => ({ value: p.id, label: p.title }))}
          />
          <Select
            style={{ minWidth: 140 }} value={days} onChange={setDays}
            options={[
              { value: 7, label: '۷ روز اخیر' },
              { value: 30, label: '۳۰ روز اخیر' },
              { value: 90, label: '۹۰ روز اخیر' },
              { value: 365, label: 'یک سال اخیر' },
            ]}
          />
          <Select
            style={{ minWidth: 140 }} placeholder="همه وضعیت‌ها" allowClear
            value={status} onChange={(v) => setStatus(v)}
            options={Object.entries(statusLabel).map(([k, v]) => ({ value: k, label: v }))}
          />
          <Button icon={<ReloadOutlined />} onClick={loadAll}>به‌روزرسانی</Button>
          {canManage && <Button type="primary" icon={<SaveOutlined />} onClick={() => setSaveOpen(true)}>ذخیره پیکربندی</Button>}
        </Space>
      </div>

      <Spin spinning={loading}>
        {overview && (
          <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
            <Col xs={12} md={6} lg={3}><Card size="small"><Statistic title="مجموع نمونه‌ها" value={overview.instances.total} /></Card></Col>
            <Col xs={12} md={6} lg={3}><Card size="small"><Statistic title="در جریان" value={overview.instances.by_status.running} valueStyle={{ color: '#3b82f6' }} /></Card></Col>
            <Col xs={12} md={6} lg={3}><Card size="small"><Statistic title="تکمیل‌شده" value={overview.instances.by_status.completed} valueStyle={{ color: '#10b981' }} /></Card></Col>
            <Col xs={12} md={6} lg={3}><Card size="small"><Statistic title="نرخ تکمیل" value={overview.instances.completion_rate} suffix="٪" /></Card></Col>
            <Col xs={12} md={6} lg={3}><Card size="small"><Statistic title="میانگین چرخه" value={fmtDuration(overview.cycle_time_seconds.avg)} prefix={<ClockCircleOutlined />} /></Card></Col>
            <Col xs={12} md={6} lg={3}><Card size="small"><Statistic title="صدک ۹۵ چرخه" value={fmtDuration(overview.cycle_time_seconds.p95)} /></Card></Col>
            <Col xs={12} md={6} lg={3}><Card size="small"><Statistic title="میانگین رسیدگی وظیفه" value={fmtDuration(overview.tasks.avg_handling_seconds)} /></Card></Col>
            <Col xs={12} md={6} lg={3}><Card size="small"><Statistic title="نرخ فرازدگی SLA" value={overview.sla.breach_rate} suffix="٪"
              valueStyle={{ color: overview.sla.breach_rate > 0 ? '#ef4444' : undefined }} prefix={<ThunderboltOutlined />} /></Card></Col>
            <Col xs={12} md={6} lg={3}><Card size="small"><Statistic title="وظایف فعال" value={overview.tasks.ready + overview.tasks.claimed} /></Card></Col>
            <Col xs={12} md={6} lg={3}><Card size="small"><Statistic title="سرریز فعال" value={overview.tasks.overdue_active}
              valueStyle={{ color: overview.tasks.overdue_active > 0 ? '#ef4444' : undefined }} /></Card></Col>
            <Col xs={12} md={6} lg={2}><Card size="small"><Statistic title="هشدار SLA" value={overview.sla.warned} /></Card></Col>
            <Col xs={12} md={6} lg={2}><Card size="small"><Statistic title="فرازدگی SLA" value={overview.sla.escalated} /></Card></Col>
          </Row>
        )}

        <Row gutter={[12, 12]}>
          <Col xs={24} lg={14}>
            <Card size="small" title={<span><BarChartOutlined /> حجم روزانه (شروع / تکمیل)</span>}>
              <MiniBars rows={volume} />
            </Card>
          </Col>
          <Col xs={24} lg={10}>
            <Card size="small" title={<span><TeamOutlined /> گزارش‌های ذخیره‌شده</span>} extra={
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>اجرا با پیکربندی ذخیره‌شده</Typography.Text>
            }>
              <Table
                size="small" rowKey="id" columns={savedCols} dataSource={saved}
                pagination={false} locale={{ emptyText: 'گزارشی ذخیره نشده است' }}
                scroll={{ x: true }}
              />
            </Card>
          </Col>
        </Row>

        <Card size="small" style={{ marginTop: 12 }}>
          <Tabs
            items={[
              {
                key: 'bottlenecks',
                label: <span><RiseOutlined /> گلوگاه‌های فرایند</span>,
                children: (
                  <Table
                    size="small" rowKey="spec_id" columns={bottleneckCols} dataSource={bottlenecks}
                    pagination={{ pageSize: 10, showSizeChanger: false }}
                    locale={{ emptyText: 'داده‌ای در این بازه نیست' }} scroll={{ x: true }}
                  />
                ),
              },
              {
                key: 'workload',
                label: <span><TeamOutlined /> بار کاری افراد و صف‌ها</span>,
                children: (
                  <Table
                    size="small" rowKey={(r) => `${r.kind}-${r.ref}`} columns={workloadCols} dataSource={workload}
                    pagination={{ pageSize: 10, showSizeChanger: false }}
                    locale={{ emptyText: 'داده‌ای در این بازه نیست' }} scroll={{ x: true }}
                  />
                ),
              },
            ]}
          />
        </Card>
      </Spin>

      <Modal
        title="ذخیره پیکربندی فعلی گزارش" open={saveOpen} onOk={saveCurrent}
        onCancel={() => setSaveOpen(false)} okText="ذخیره" cancelText="انصراف"
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Input placeholder="نام گزارش" value={saveName} onChange={(e) => setSaveName(e.target.value)} />
          <Input.TextArea placeholder="توضیح (اختیاری)" rows={2} value={saveDesc} onChange={(e) => setSaveDesc(e.target.value)} />
          <Select
            style={{ width: '100%' }} value={saveDataset} onChange={setSaveDataset}
            options={Object.entries(DATASET_TITLES).map(([k, v]) => ({ value: k, label: `مجموعه‌داده: ${v}` }))}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            فیلترهای فعلی (بازه، فرایند، وضعیت) همراه گزارش ذخیره می‌شود.
          </Typography.Text>
        </Space>
      </Modal>
    </div>
  );
}
