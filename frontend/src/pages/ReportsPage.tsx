// گزارش‌ساز و KPI — فاز ۶ + نمودارهای تعاملی و خروجی Excel/PDF (فاز ۷)
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button, Card, Col, Empty, Input, Modal, Row, Select, Space, Spin, Statistic,
  Table, Tabs, Tag, Tooltip, Typography, App,
} from 'antd';
import {
  BarChartOutlined, ClockCircleOutlined, DeleteOutlined,
  ExclamationCircleOutlined, FileExcelOutlined, FilePdfOutlined, LineChartOutlined,
  PieChartOutlined, ReloadOutlined, RiseOutlined, SaveOutlined, TeamOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import type { EChartsOption } from 'echarts';
import { api, extractError } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { gregorianToJalaliStr } from '../lib/persian';
import EChart, { CHART_COLORS, baseText } from '../components/EChart';

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

const statusLabel: Record<string, string> = {
  running: 'در جریان', completed: 'تکمیل‌شده', cancelled: 'لغوشده', error: 'خطا',
};
const STATUS_COLORS: Record<string, string> = {
  running: CHART_COLORS.blue, completed: CHART_COLORS.green,
  cancelled: CHART_COLORS.slate, error: CHART_COLORS.red,
};

function fmtDuration(sec: number | null | undefined): string {
  if (sec === null || sec === undefined || Number.isNaN(sec)) return '—';
  if (sec === 0) return '۰';
  if (sec < 60) return `${Math.round(sec)} ثانیه`;
  if (sec < 3600) return `${(sec / 60).toFixed(1)} دقیقه`;
  if (sec < 86400) return `${(sec / 3600).toFixed(1)} ساعت`;
  return `${(sec / 86400).toFixed(1)} روز`;
}

/** برچسب کوتاه جلالی برای محور زمان نمودار («۰۵/۰۷») */
function jShort(iso: string): string {
  const j = gregorianToJalaliStr(iso);
  return j ? j.slice(5) : iso.slice(5);
}

const faNum = (n: number | string) => Number(n).toLocaleString('fa-IR');

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
  const [exporting, setExporting] = useState<string | null>(null);

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

  // ---------- خروجی Excel / PDF (فاز ۷) ----------

  const saveBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 3000);
  };

  const exportAll = async (fmt: 'excel' | 'pdf') => {
    setExporting(fmt);
    try {
      const resp = await api.get(`/reports/export/${fmt}`, { params, responseType: 'blob' });
      saveBlob(resp.data as Blob, fmt === 'excel' ? 'bpms-report.xlsx' : 'bpms-report.pdf');
      message.success(fmt === 'excel' ? 'خروجی Excel آماده شد' : 'خروجی PDF آماده شد');
    } catch (e) {
      message.error(extractError(e));
    } finally {
      setExporting(null);
    }
  };

  const exportSaved = async (r: SavedReportRow, fmt: 'excel' | 'pdf') => {
    setExporting(`saved-${r.id}-${fmt}`);
    try {
      const resp = await api.get(`/reports/saved/${r.id}/export`,
        { params: { format: fmt }, responseType: 'blob' });
      saveBlob(resp.data as Blob, `bpms-saved-${r.id}.${fmt === 'excel' ? 'xlsx' : 'pdf'}`);
      message.success(`خروجی ${fmt === 'excel' ? 'Excel' : 'PDF'} گزارش «${r.name}» آماده شد`);
    } catch (e) {
      message.error(extractError(e));
    } finally {
      setExporting(null);
    }
  };

  // ---------- گزارش‌های ذخیره‌شده ----------

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
        message.info(`${DATASET_TITLES[r.dataset] || r.dataset}: ${d.items.length} ردیف`);
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

  // ---------- گزینه‌های نمودارهای تعاملی (ECharts) ----------

  const volumeOption = useMemo<EChartsOption>(() => {
    const shown = volume.slice(-60);
    return {
      textStyle: baseText(),
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: (ps: unknown) => {
          const list = ps as { marker: string; name: string; seriesName: string; value: number }[];
          const head = `<div style="font-weight:600">${gregorianToJalaliStr(String(list[0]?.name)) || list[0]?.name}</div>`;
          return head + list.map((p) =>
            `${p.marker} ${p.seriesName}: <b>${faNum(p.value)}</b>`).join('<br/>');
        },
      },
      legend: { data: ['شروع‌شده', 'تکمیل‌شده'], bottom: 30, textStyle: baseText({ fontSize: 12 }) },
      grid: { left: 8, right: 12, top: 40, bottom: 70, containLabel: true },
      xAxis: {
        type: 'category', data: shown.map((r) => r.date),
        axisLabel: { formatter: (v: string) => jShort(v), fontFamily: 'Vazirmatn', fontSize: 10 },
        axisTick: { alignWithLabel: true },
      },
      yAxis: { type: 'value', minInterval: 1, axisLabel: { formatter: (v: number) => faNum(v) } },
      dataZoom: [
        { type: 'inside' },
        { type: 'slider', height: 18, bottom: 4, brushSelect: false },
      ],
      series: [
        {
          name: 'شروع‌شده', type: 'bar', data: shown.map((r) => r.started),
          itemStyle: { color: CHART_COLORS.blue, borderRadius: [3, 3, 0, 0] },
          barMaxWidth: 18,
        },
        {
          name: 'تکمیل‌شده', type: 'line', data: shown.map((r) => r.completed),
          itemStyle: { color: CHART_COLORS.green },
          lineStyle: { width: 2.5 }, smooth: true,
          symbolSize: 6, emphasis: { focus: 'series' },
        },
      ],
    };
  }, [volume]);

  const donutOption = useMemo<EChartsOption>(() => {
    const data = Object.entries(overview?.instances.by_status ?? {})
      .filter(([, v]) => v > 0)
      .map(([k, v]) => ({ name: statusLabel[k] || k, value: v, itemStyle: { color: STATUS_COLORS[k] } }));
    return {
      textStyle: baseText(),
      tooltip: {
        trigger: 'item',
        formatter: (p: unknown) => {
          const q = p as { name: string; value: number; percent: number };
          return `${q.name}: <b>${faNum(q.value)}</b> (${faNum(q.percent)}٪)`;
        },
      },
      legend: { bottom: 0, textStyle: baseText({ fontSize: 12 }) },
      title: {
        text: faNum(overview?.instances.total ?? 0),
        subtext: 'مجموع نمونه‌ها',
        left: 'center', top: '38%',
        textStyle: { fontFamily: 'Vazirmatn', fontSize: 24, color: '#1e293b' },
        subtextStyle: { fontFamily: 'Vazirmatn', fontSize: 12, color: '#64748b' },
      },
      series: [{
        type: 'pie', radius: ['52%', '74%'], center: ['50%', '46%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 5, borderColor: '#fff', borderWidth: 2 },
        label: { show: true, formatter: '{b}\n{d}٪', fontFamily: 'Vazirmatn', fontSize: 11 },
        emphasis: { scale: true, scaleSize: 6 },
        data,
      }],
    };
  }, [overview]);

  const bottleneckOption = useMemo<EChartsOption>(() => {
    const rows = [...bottlenecks].slice(0, 10).reverse();
    return {
      textStyle: baseText(),
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: (ps: unknown) => {
          const list = ps as { marker: string; seriesName: string; value: number }[];
          return list.map((p) => `${p.marker} ${p.seriesName}: <b>${fmtDuration(p.value)}</b>`).join('<br/>');
        },
      },
      legend: { data: ['میانگین رسیدگی', 'میانگین انتظار'], top: 0, textStyle: baseText({ fontSize: 12 }) },
      grid: { left: 8, right: 24, top: 34, bottom: 8, containLabel: true },
      xAxis: {
        type: 'value',
        axisLabel: { formatter: (v: number) => fmtDuration(v), fontSize: 10, fontFamily: 'Vazirmatn' },
      },
      yAxis: {
        type: 'category', data: rows.map((r) => r.name),
        axisLabel: { fontFamily: 'Vazirmatn', fontSize: 11, width: 130, overflow: 'truncate' },
      },
      series: [
        {
          name: 'میانگین رسیدگی', type: 'bar', data: rows.map((r) => Math.round(r.avg_handling_seconds)),
          barMaxWidth: 14, itemStyle: { borderRadius: [0, 4, 4, 0] },
          color: {
            type: 'linear', x: 0, y: 0, x2: 1, y2: 0,
            colorStops: [{ offset: 0, color: '#f59e0b' }, { offset: 1, color: '#ef4444' }],
          },
          emphasis: { focus: 'series' },
        },
        {
          name: 'میانگین انتظار', type: 'bar', data: rows.map((r) => Math.round(r.avg_wait_seconds)),
          barMaxWidth: 14, itemStyle: { borderRadius: [0, 4, 4, 0], color: CHART_COLORS.blue },
        },
      ],
    };
  }, [bottlenecks]);

  const workloadOption = useMemo<EChartsOption>(() => {
    const rows = [...workload]
      .sort((a, b) => (b.completed + b.active) - (a.completed + a.active))
      .slice(0, 10).reverse();
    return {
      textStyle: baseText(),
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: (ps: unknown) => {
          const list = ps as { name: string; marker: string; seriesName: string; value: number }[];
          const head = `<div style="font-weight:600">${list[0]?.name}</div>`;
          return head + list.map((p) => `${p.marker} ${p.seriesName}: <b>${faNum(p.value)}</b>`).join('<br/>');
        },
      },
      legend: { data: ['تکمیل‌شده', 'فعال', 'سرریز فعال'], top: 0, textStyle: baseText({ fontSize: 12 }) },
      grid: { left: 8, right: 24, top: 34, bottom: 8, containLabel: true },
      xAxis: { type: 'value', minInterval: 1, axisLabel: { formatter: (v: number) => faNum(v) } },
      yAxis: {
        type: 'category', data: rows.map((r) => r.label),
        axisLabel: { fontFamily: 'Vazirmatn', fontSize: 11, width: 130, overflow: 'truncate' },
      },
      series: [
        { name: 'تکمیل‌شده', type: 'bar', stack: 'w', data: rows.map((r) => r.completed), itemStyle: { color: CHART_COLORS.green }, barMaxWidth: 16 },
        { name: 'فعال', type: 'bar', stack: 'w', data: rows.map((r) => r.active), itemStyle: { color: CHART_COLORS.blue }, barMaxWidth: 16 },
        { name: 'سرریز فعال', type: 'bar', stack: 'w', data: rows.map((r) => r.overdue_active), itemStyle: { color: CHART_COLORS.red }, barMaxWidth: 16 },
      ],
    };
  }, [workload]);

  // ---------- ستون‌های جدول ----------

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
      <Space size={4} wrap>
        <Button size="small" icon={<BarChartOutlined />} onClick={() => runSaved(r)}>اجرا</Button>
        <Tooltip title="خروجی Excel"><Button size="small" data-testid={`saved-export-excel-${r.id}`}
          icon={<FileExcelOutlined style={{ color: '#059669' }} />}
          loading={exporting === `saved-${r.id}-excel`}
          onClick={() => exportSaved(r, 'excel')} /></Tooltip>
        <Tooltip title="خروجی PDF"><Button size="small" data-testid={`saved-export-pdf-${r.id}`}
          icon={<FilePdfOutlined style={{ color: '#dc2626' }} />}
          loading={exporting === `saved-${r.id}-pdf`}
          onClick={() => exportSaved(r, 'pdf')} /></Tooltip>
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
          <Tooltip title="خروجی Excel — کتاب‌کار چندبرگی از همه شاخص‌ها">
            <Button data-testid="export-excel" icon={<FileExcelOutlined style={{ color: '#059669' }} />}
              loading={exporting === 'excel'} onClick={() => exportAll('excel')}>خروجی Excel</Button>
          </Tooltip>
          <Tooltip title="خروجی PDF فارسی (راست‌به‌چپ)">
            <Button data-testid="export-pdf" icon={<FilePdfOutlined style={{ color: '#dc2626' }} />}
              loading={exporting === 'pdf'} onClick={() => exportAll('pdf')}>خروجی PDF</Button>
          </Tooltip>
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
            <Col xs={12} md={6} lg={3}><Card size="small"><Statistic title="هشدار SLA" value={overview.sla.warned} /></Card></Col>
            <Col xs={12} md={6} lg={3}><Card size="small"><Statistic title="فرازدگی SLA" value={overview.sla.escalated} /></Card></Col>
          </Row>
        )}

        <Row gutter={[12, 12]}>
          <Col xs={24} lg={16}>
            <Card size="small" title={<span><LineChartOutlined /> حجم روزانه (شروع / تکمیل) — تعاملی با زوم</span>}>
              <EChart option={volumeOption} height={330} testid="volume-chart" />
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card size="small" title={<span><PieChartOutlined /> ترکیب وضعیت نمونه‌ها</span>}>
              {(overview?.instances.total ?? 0) > 0
                ? <EChart option={donutOption} height={330} testid="status-donut" />
                : <Empty description="نمونه‌ای در این بازه نیست" style={{ paddingTop: 90 }} />}
            </Card>
          </Col>
        </Row>

        <Card size="small" title={<span><TeamOutlined /> گزارش‌های ذخیره‌شده</span>} extra={
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>اجرا و خروجی Excel/PDF با پیکربندی ذخیره‌شده</Typography.Text>
        } style={{ marginTop: 12 }}>
          <Table
            size="small" rowKey="id" columns={savedCols} dataSource={saved}
            pagination={false} locale={{ emptyText: 'گزارشی ذخیره نشده است' }}
            scroll={{ x: true }}
          />
        </Card>

        <Card size="small" style={{ marginTop: 12 }}>
          <Tabs
            items={[
              {
                key: 'bottlenecks',
                label: <span><RiseOutlined /> گلوگاه‌های فرایند</span>,
                children: (
                  <>
                    {bottlenecks.length > 0
                      ? <EChart option={bottleneckOption} height={300} testid="bottleneck-chart" />
                      : <Empty description="داده‌ای در این بازه نیست" />}
                    <Table
                      style={{ marginTop: 8 }}
                      size="small" rowKey="spec_id" columns={bottleneckCols} dataSource={bottlenecks}
                      pagination={{ pageSize: 10, showSizeChanger: false }}
                      locale={{ emptyText: 'داده‌ای در این بازه نیست' }} scroll={{ x: true }}
                    />
                  </>
                ),
              },
              {
                key: 'workload',
                label: <span><TeamOutlined /> بار کاری افراد و صف‌ها</span>,
                children: (
                  <>
                    {workload.length > 0
                      ? <EChart option={workloadOption} height={300} testid="workload-chart" />
                      : <Empty description="داده‌ای در این بازه نیست" />}
                    <Table
                      style={{ marginTop: 8 }}
                      size="small" rowKey={(r) => `${r.kind}-${r.ref}`} columns={workloadCols} dataSource={workload}
                      pagination={{ pageSize: 10, showSizeChanger: false }}
                      locale={{ emptyText: 'داده‌ای در این بازه نیست' }} scroll={{ x: true }}
                    />
                  </>
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
            فیلترهای فعلی (بازه، فرایند، وضعیت) همراه گزارش ذخیره می‌شود. خروجی Excel/PDF نیز برای هر گزارش ذخیره‌شده در دسترس است.
          </Typography.Text>
        </Space>
      </Modal>
    </div>
  );
}
