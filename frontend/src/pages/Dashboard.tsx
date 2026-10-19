// داشبورد — شاخص‌های کارتابل و دسترسی سریع
import { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Typography, List, Tag, Button } from 'antd';
import { CheckSquareOutlined, SolutionOutlined, ClockCircleOutlined, PartitionOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { api, TaskRow } from '../api/client';
import { useAuth } from '../auth/AuthContext';

const STATUS_COLORS: Record<string, string> = {
  running: 'processing', completed: 'success', cancelled: 'default', error: 'error',
};

export default function Dashboard() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [inbox, setInbox] = useState<TaskRow[]>([]);
  const [group, setGroup] = useState(0);
  const [myReqs, setMyReqs] = useState(0);
  const [running, setRunning] = useState(0);

  useEffect(() => {
    api.get('/tasks/inbox', { params: { page_size: 6 } }).then((r) => setInbox(r.data.items)).catch(() => {});
    api.get('/tasks/group', { params: { page_size: 1 } }).then((r) => setGroup(r.data.total)).catch(() => {});
    api.get('/process-instances', { params: { scope: 'mine', page_size: 1 } }).then((r) => setMyReqs(r.data.total)).catch(() => {});
    api.get('/process-instances', { params: { status: 'running', page_size: 1 } }).then((r) => setRunning(r.data.total)).catch(() => {});
  }, []);

  return (
    <div>
      <Typography.Title level={4}>خوش آمدید، {user?.full_name} 👋</Typography.Title>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card><Statistic title="وظایف تخصیص‌یافته به من" value={inbox.length} suffix={<CheckSquareOutlined style={{ fontSize: 20 }} />} />
            <Button type="link" onClick={() => nav('/inbox')}>مشاهده کارتابل</Button></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card><Statistic title="صف گروهی قابل دریافت" value={group} suffix={<ClockCircleOutlined style={{ fontSize: 20 }} />} />
            <Button type="link" onClick={() => nav('/inbox?tab=group')}>مشاهده صف</Button></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card><Statistic title="درخواست‌های من" value={myReqs} suffix={<SolutionOutlined style={{ fontSize: 20 }} />} />
            <Button type="link" onClick={() => nav('/my-requests')}>مشاهده</Button></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card><Statistic title="نمونه‌های در جریان (کل سامانه)" value={running} suffix={<PartitionOutlined style={{ fontSize: 20 }} />} />
            <Button type="link" onClick={() => nav('/monitor')}>پایش</Button></Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col xs={24} md={14}>
          <Card title="آخرین وظایف من" size="small">
            <List
              size="small"
              dataSource={inbox}
              locale={{ emptyText: 'وظیفه‌ای ندارید — کارتان خالی است' }}
              renderItem={(t) => (
                <List.Item actions={[<Button size="small" type="link" onClick={() => nav(`/inbox?task=${t.id}`)}>انجام</Button>]}>
                  <List.Item.Meta
                    title={`${t.name} — ${t.instance?.process_title}`}
                    description={`نمونه #${t.instance_id} • ${t.created_at_jalali || ''}`}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} md={10}>
          <Card title="راهنمای سریع" size="small">
            <List size="small" dataSource={[
              'ثبت درخواست جدید از منوی «فرایندها»',
              'انجام وظایف از «کارتابل» (وظایف گروهی ابتدا باید دریافت شوند)',
              'پیگیری وضعیت و نمودار زنده در «درخواست‌های من»',
              'طراحی فرم و فرایند برای مدیران سامانه از منوی مرتبط',
            ]} renderItem={(it) => <List.Item><Typography.Text>{it}</Typography.Text></List.Item>} />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
