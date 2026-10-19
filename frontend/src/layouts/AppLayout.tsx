import { useMemo, useState } from 'react';
import { Badge, Dropdown, Layout, Menu, Popover, List, App, Tag } from 'antd';
import {
  AuditOutlined, BellOutlined, DashboardOutlined, DatabaseOutlined, ApartmentOutlined,
  LogoutOutlined, PartitionOutlined, SolutionOutlined, TeamOutlined, UserOutlined,
  ClusterOutlined, FormOutlined, EyeOutlined, CheckSquareOutlined,
  TableOutlined, CalendarOutlined, BarChartOutlined,
} from '@ant-design/icons';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import { api } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { useLiveEvents, dispatchUiEvent, EVT_INBOX_REFRESH, LiveEvent } from '../lib/liveEvents';

const { Header, Sider, Content } = Layout;

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, logout, hasPerm } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [unread, setUnread] = useState(0);
  const [live, setLive] = useState(false);
  const [notifs, setNotifs] = useState<{ id: number; title: string; body: string | null; is_read: boolean }[]>([]);
  const { message } = App.useApp();

  // اتصال زنده (SSE) — فاز ۳
  useLiveEvents({
    onEvent: (ev: LiveEvent) => {
      if (ev.type === 'hello') { setLive(true); return; }
      if (ev.type === 'notification') {
        setUnread((u) => u + 1);
        const title = String(ev.data?.title || 'اعلان جدید');
        const body = String(ev.data?.body || '');
        message.open({ type: 'info', content: `${title}${body ? ' — ' + body : ''}`, duration: 6 });
        dispatchUiEvent(EVT_INBOX_REFRESH, { reason: 'notification' });
        // به‌روزرسانی فهرست اعلان‌ها
        api.get('/notifications', { params: { unread_only: false } }).then((r) => {
          setNotifs(r.data.items.slice(0, 8));
          setUnread(r.data.unread || 0);
        }).catch(() => {});
      }
      if (ev.type === 'instance' || ev.type === 'sla') {
        dispatchUiEvent(EVT_INBOX_REFRESH, { reason: ev.type, data: ev.data });
      }
    },
  });

  const menuItems = useMemo(() => {
    const items: { key: string; icon: React.ReactNode; label: string }[] = [
      { key: '/', icon: <DashboardOutlined />, label: 'داشبورد' },
    ];
    if (hasPerm('task.complete') || user?.is_superadmin) items.push({ key: '/inbox', icon: <CheckSquareOutlined />, label: 'کارتابل' });
    items.push({ key: '/my-requests', icon: <SolutionOutlined />, label: 'درخواست‌های من' });
    if (hasPerm('process.start')) items.push({ key: '/processes', icon: <PartitionOutlined />, label: 'فرایندها' });
    if (hasPerm('form.view')) items.push({ key: '/forms', icon: <FormOutlined />, label: 'فرم‌ها' });
    if (hasPerm('decision.view') || user?.is_superadmin) items.push({ key: '/decisions', icon: <TableOutlined />, label: 'جدول‌های تصمیم' });
    if (hasPerm('calendar.view') || user?.is_superadmin) items.push({ key: '/calendars', icon: <CalendarOutlined />, label: 'تقویم کاری' });
    if (hasPerm('monitor.view')) items.push({ key: '/monitor', icon: <EyeOutlined />, label: 'پایش فرایندها' });
    if (hasPerm('report.view') || user?.is_superadmin) items.push({ key: '/reports', icon: <BarChartOutlined />, label: 'گزارش‌ساز و KPI' });
    if (hasPerm('lookup.manage')) items.push({ key: '/lookups', icon: <DatabaseOutlined />, label: 'داده‌های پایه' });
    if (hasPerm('org.manage')) items.push({ key: '/org', icon: <ApartmentOutlined />, label: 'ساختار سازمانی' });
    if (hasPerm('user.manage')) items.push({ key: '/users', icon: <TeamOutlined />, label: 'کاربران و نقش‌ها' });
    if (hasPerm('audit.view')) items.push({ key: '/audit', icon: <AuditOutlined />, label: 'ممیزی' });
    return items;
  }, [hasPerm, user]);

  useEffect(() => {
    const fetchNotifs = () => {
      api.get('/notifications', { params: { unread_only: false } }).then((r) => {
        setNotifs(r.data.items.slice(0, 8));
        setUnread(r.data.unread || 0);
      }).catch(() => {});
    };
    fetchNotifs();
    const t = setInterval(fetchNotifs, 15000);
    return () => clearInterval(t);
  }, []);

  const markAll = async () => {
    await api.post('/notifications/read-all');
    setUnread(0);
    message.success('همه اعلان‌ها خوانده شد');
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed} theme="dark" width={230}>
        <div style={{ height: 56, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 700, fontSize: collapsed ? 12 : 16, borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          {collapsed ? 'BPMS' : 'سامانه BPMS'}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[loc.pathname]}
          items={menuItems}
          onClick={({ key }) => nav(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #e5e7eb', height: 56 }}>
          <div />
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {live && <Tag color="green" style={{ marginInlineEnd: 0 }}>زنده</Tag>}
            <Popover
              trigger="click"
              placement="bottomLeft"
              title={
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>اعلان‌ها</span>
                  <a onClick={markAll}>خواندن همه</a>
                </div>
              }
              content={
                <List size="small" style={{ width: 320, maxHeight: 320, overflow: 'auto' }}
                  dataSource={notifs}
                  locale={{ emptyText: 'اعلانی نیست' }}
                  renderItem={(n) => (
                    <List.Item>
                      <div>
                        <div style={{ fontWeight: n.is_read ? 400 : 700 }}>{n.title}</div>
                        <div style={{ fontSize: 12, color: '#6b7280' }}>{n.body}</div>
                      </div>
                    </List.Item>
                  )}
                />
              }
            >
              <Badge count={unread} size="small">
                <BellOutlined style={{ fontSize: 18, cursor: 'pointer' }} />
              </Badge>
            </Popover>
            <Dropdown menu={{
              items: [{ key: 'logout', icon: <LogoutOutlined />, label: 'خروج' }],
              onClick: ({ key }) => { if (key === 'logout') logout(); },
            }}>
              <span style={{ cursor: 'pointer' }}>
                <UserOutlined /> {user?.full_name}
              </span>
            </Dropdown>
          </div>
        </Header>
        <Content style={{ margin: 16 }}>{children}</Content>
      </Layout>
    </Layout>
  );
}
