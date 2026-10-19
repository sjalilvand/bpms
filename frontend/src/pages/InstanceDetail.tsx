// جزئیات نمونه اجرایی — نمودار زنده، تاریخچه، وظایف، خطاها و لغو
import { useCallback, useEffect, useState } from 'react';
import { Button, Card, Col, Descriptions, Modal, Row, Space, Table, Tabs, Tag, Timeline, Typography, App as AntApp, Popconfirm } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import { api, InstanceDetailT, extractError } from '../api/client';
import BpmnViewer from '../components/BpmnViewer';

const EVENT_LABELS: Record<string, string> = {
  instance_started: 'شروع نمونه', instance_completed: 'تکمیل نمونه',
  instance_cancelled: 'لغو نمونه', task_created: 'ایجاد وظیفه',
  task_claimed: 'دریافت وظیفه', task_released: 'آزادسازی وظیفه',
  task_completed: 'تکمیل وظیفه', task_cancelled: 'لغو وظیفه',
  incident_created: 'خطا (قابل رسیدگی)', incident_resolved: 'رفع خطا',
};

export default function InstanceDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { message } = AntApp.useApp();
  const [detail, setDetail] = useState<InstanceDetailT | null>(null);
  const [xml, setXml] = useState('');
  const [state, setState] = useState<{ active: string[]; completed: string[]; error: string[] }>({ active: [], completed: [], error: [] });

  const load = useCallback(async () => {
    try {
      const r = await api.get<InstanceDetailT>(`/process-instances/${id}`);
      setDetail(r.data);
      // XML نسخه ثابت نمونه (نمودار نسخه واقعی اجرا — نه آخرین نسخه)
      const v = await api.get(`/processes/versions/${r.data.version_id}`);
      setXml(v.data.bpmn_xml);
      const s = await api.get(`/process-instances/${id}/state`);
      setState(s.data);
    } catch (e) { message.error(extractError(e)); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // به‌روزرسانی زنده نمونه از رویدادهای SSE (فاز ۳)
  useEffect(() => {
    const onRefresh = (e: Event) => {
      const detail = (e as CustomEvent).detail || {};
      if (detail?.instance_id && Number(detail.instance_id) !== Number(id)) return;
      load();
    };
    window.addEventListener('bpms:inbox-refresh', onRefresh);
    return () => window.removeEventListener('bpms:inbox-refresh', onRefresh);
  }, [load, id]);

  const cancel = async (reason: string) => {
    try {
      await api.post(`/process-instances/${id}/cancel`, { reason });
      message.success('نمونه لغو شد');
      load();
    } catch (e) { message.error(extractError(e)); }
  };

  const resolveIncident = async (incidentId: number) => {
    try {
      // رسیدگی به خطا از طریق endpoint عمومی incidents
      await api.post(`/incidents/${incidentId}/retry`);
      message.success('تلاش مجدد انجام شد');
      load();
    } catch (e) { message.error(extractError(e)); }
  };

  if (!detail) return <Card loading title="جزئیات نمونه" />;

  return (
    <div>
      <Button icon={<ArrowRightOutlined />} type="link" onClick={() => nav(-1)} style={{ marginBottom: 8 }}>بازگشت</Button>
      <Card
        title={`نمونه #${detail.id} — ${detail.title}`}
        extra={
          <Space>
            <Tag color={detail.status === 'running' ? 'processing' : detail.status === 'completed' ? 'success' : detail.status === 'error' ? 'error' : 'default'}>
              {detail.status === 'running' ? 'در جریان' : detail.status === 'completed' ? 'تکمیل‌شده' : detail.status === 'error' ? 'خطادار' : 'لغوشده'}
            </Tag>
            <Button size="small" onClick={load}>بررسی تایمر/به‌روزرسانی</Button>
          </Space>
        }
      >
        <Descriptions size="small" column={4}>
          <Descriptions.Item label="فرایند">{detail.process?.title}</Descriptions.Item>
          <Descriptions.Item label="نسخه مدل">{detail.version}</Descriptions.Item>
          <Descriptions.Item label="درخواست‌دهنده">{detail.started_by}</Descriptions.Item>
          <Descriptions.Item label="زمان شروع">{detail.started_at_jalali}</Descriptions.Item>
        </Descriptions>

        {detail.incidents.length > 0 && (
          <Card size="small" style={{ marginTop: 12, borderColor: '#fca5a5', background: '#fef2f2' }} title="موارد قابل رسیدگی">
            {detail.incidents.map((x) => (
              <div key={x.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
                <Typography.Text type="danger">[{x.spec_id}] {x.message}</Typography.Text>
                <Popconfirm title="تلاش مجدد برای این فعالیت؟" onConfirm={() => resolveIncident(x.id)}>
                  <Button size="small" danger>تلاش مجدد</Button>
                </Popconfirm>
              </div>
            ))}
          </Card>
        )}

        <Tabs style={{ marginTop: 12 }} items={[
          {
            key: 'diagram', label: 'نمودار زنده',
            children: (
              <div>
                <Space style={{ marginBottom: 8 }}>
                  <Tag color="processing">فعال</Tag>
                  <Tag color="success">تکمیل‌شده</Tag>
                  <Tag color="error">خطادار</Tag>
                </Space>
                {xml ? <BpmnViewer xml={xml} active={state.active} completed={state.completed} error={state.error} /> : <Card loading />}
              </div>
            ),
          },
          {
            key: 'tasks', label: `وظایف (${detail.tasks.length})`,
            children: (
              <Table rowKey="id" size="small" pagination={false} dataSource={detail.tasks}
                columns={[
                  { title: 'عنوان', dataIndex: 'name' },
                  { title: 'شناسه فنی', dataIndex: 'spec_id', render: (v: string) => <span className="mono">{v}</span> },
                  {
                    title: 'وضعیت', dataIndex: 'status', render: (s: string) => (
                      <Tag color={s === 'completed' ? 'success' : s === 'ready' ? 'processing' : s === 'claimed' ? 'warning' : 'default'}>{s}</Tag>
                    ),
                  },
                  { title: 'مسئول', dataIndex: 'assignee', render: (v: string | null, r) => v || (r.candidate_role ? `نقش: ${r.candidate_role}` : '—') },
                  { title: 'نتیجه', dataIndex: 'result', render: (v: string | null) => v || '—' },
                  { title: 'نظر', dataIndex: 'comment', ellipsis: true, render: (v: string | null) => v || '—' },
                ]} />
            ),
          },
          {
            key: 'history', label: 'تاریخچه',
            children: (
              <Timeline
                items={detail.history.map((h) => ({
                  color: h.event_type === 'task_completed' || h.event_type === 'instance_completed' ? 'green'
                    : h.event_type.includes('incident') ? 'red' : 'blue',
                  children: (
                    <div>
                      <b>{EVENT_LABELS[h.event_type] || h.event_type}</b>
                      {h.task_name ? ` — ${h.task_name}` : ''}
                      {h.actor ? ` (${h.actor})` : ''}
                      {h.comment ? <div><Typography.Text type="secondary">{h.comment}</Typography.Text></div> : null}
                      <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>{h.created_at_jalali}</Typography.Text></div>
                    </div>
                  ),
                }))}
              />
            ),
          },
        ]} />
      </Card>
    </div>
  );
}
