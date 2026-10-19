// کاربران، نقش‌ها و مجوزها + جانشینی
import { useCallback, useEffect, useState } from 'react';
import {
  Button, Card, Checkbox, Form, Input, Modal, Select, Space, Table, Tabs, Tag,
  DatePicker, App as AntApp, Switch, Typography,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { api, Paged, UserInfo, extractError } from '../api/client';

interface RoleT { id: number; code: string; title: string; description: string; permissions: string[] }

export default function UsersPage() {
  const { message } = AntApp.useApp();
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [roles, setRoles] = useState<RoleT[]>([]);
  const [perms, setPerms] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [userModal, setUserModal] = useState<null | { user?: UserInfo }>(null);
  const [roleModal, setRoleModal] = useState(false);
  const [delegModal, setDelegModal] = useState(false);
  const [delegs, setDelegs] = useState<any[]>([]);
  const [uForm] = Form.useForm();
  const [rForm] = Form.useForm();
  const [dForm] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [u, r, p] = await Promise.all([
        api.get<Paged<UserInfo>>('/users', { params: { page_size: 100 } }),
        api.get('/roles'),
        api.get('/permissions'),
      ]);
      setUsers(u.data.items);
      setRoles(r.data.items);
      setPerms(p.data.items);
    } catch (e) { message.error(extractError(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const saveUser = async () => {
    try {
      const v = await uForm.validateFields();
      const payload = { ...v, role_ids: v.role_ids || [], is_active: v.is_active ?? true };
      if (userModal?.user) {
        await api.put(`/users/${userModal.user.id}`, payload);
      } else {
        await api.post('/users', payload);
      }
      message.success('ذخیره شد');
      setUserModal(null);
      uForm.resetFields();
      load();
    } catch (e: any) { if (!e?.errorFields) message.error(extractError(e)); }
  };

  const saveRole = async () => {
    try {
      const v = await rForm.validateFields();
      await api.post('/roles', v);
      message.success('نقش ایجاد شد');
      setRoleModal(false);
      rForm.resetFields();
      load();
    } catch (e: any) { if (!e?.errorFields) message.error(extractError(e)); }
  };

  const saveDeleg = async () => {
    try {
      const v = await dForm.validateFields();
      await api.post('/delegations', {
        from_user_id: v.from_user_id,
        to_user_id: v.to_user_id,
        start_date: v.range[0]?.format('YYYY-MM-DD'),
        end_date: v.range[1]?.format('YYYY-MM-DD'),
        note: v.note || '',
      });
      message.success('جانشینی ثبت شد');
      setDelegModal(false);
      dForm.resetFields();
      loadDelegs();
    } catch (e: any) { if (!e?.errorFields) message.error(extractError(e)); }
  };

  const loadDelegs = async () => {
    try { const r = await api.get('/delegations'); setDelegs(r.data.items); } catch { setDelegs([]); }
  };

  return (
    <Card title="مدیریت کاربران، نقش‌ها و جانشینی"
      extra={<Space><Button icon={<ReloadOutlined />} onClick={load} /></Space>}>
      <Tabs items={[
        {
          key: 'users', label: 'کاربران',
          children: (
            <>
              <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 12 }}
                onClick={() => { setUserModal({}); uForm.resetFields(); }}>کاربر جدید</Button>
              <Table rowKey="id" size="small" loading={loading} dataSource={users}
                columns={[
                  { title: 'نام', dataIndex: 'full_name' },
                  { title: 'نام کاربری', dataIndex: 'username', render: (v: string) => <span className="mono">{v}</span> },
                  { title: 'نقش‌ها', key: 'roles', render: (_: unknown, u: UserInfo) => u.roles.map((r) => <Tag key={r.id}>{r.title}</Tag>) },
                  { title: 'فعال', dataIndex: 'is_active', render: (v: boolean) => v ? <Tag color="success">فعال</Tag> : <Tag>غیرفعال</Tag> },
                  { title: 'مدیر کل', dataIndex: 'is_superadmin', render: (v: boolean) => v ? <Tag color="purple">بله</Tag> : '—' },
                  {
                    title: '', key: 'act',
                    render: (_: unknown, u: UserInfo) => (
                      <Button size="small" type="link" onClick={() => {
                        setUserModal({ user: u });
                        uForm.setFieldsValue({ ...u, role_ids: u.roles.map((r) => r.id), password: undefined });
                      }}>ویرایش</Button>
                    ),
                  },
                ]} />
            </>
          ),
        },
        {
          key: 'roles', label: 'نقش‌ها و مجوزها',
          children: (
            <>
              <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 12 }} onClick={() => setRoleModal(true)}>نقش جدید</Button>
              <Table rowKey="id" size="small" dataSource={roles} pagination={false}
                columns={[
                  { title: 'عنوان', dataIndex: 'title' },
                  { title: 'کد', dataIndex: 'code', render: (v: string) => <span className="mono">{v}</span> },
                  {
                    title: 'مجوزها', dataIndex: 'permissions',
                    render: (ps: string[]) => ps.includes('*')
                      ? <Tag color="purple">همه مجوزها</Tag>
                      : ps.map((p) => <Tag key={p} style={{ fontSize: 11 }}>{p}</Tag>),
                  },
                ]} />
            </>
          ),
        },
        {
          key: 'delegation', label: 'جانشینی',
          children: (
            <>
              <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 12 }}
                onClick={() => { setDelegModal(true); loadDelegs(); }}>جانشینی جدید</Button>
              <Table rowKey="id" size="small" dataSource={delegs} pagination={false}
                columns={[
                  { title: 'از کاربر', dataIndex: 'from_user_id' },
                  { title: 'جانشین', dataIndex: 'to_user_id' },
                  { title: 'از تاریخ', dataIndex: 'start_date' },
                  { title: 'تا تاریخ', dataIndex: 'end_date' },
                  { title: 'فعال', dataIndex: 'is_active', render: (v: boolean) => v ? <Tag color="success">فعال</Tag> : <Tag>خیر</Tag> },
                ]} />
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                وظایف کاربر اصلی در بازه جانشینی، در کارتابل جانشین نیز ظاهر می‌شود.
              </Typography.Text>
            </>
          ),
        },
      ]} />

      {/* کاربر */}
      <Modal open={!!userModal} title={userModal?.user ? 'ویرایش کاربر' : 'کاربر جدید'} onCancel={() => setUserModal(null)} onOk={saveUser} okText="ذخیره">
        <Form form={uForm} layout="vertical">
          <Form.Item name="full_name" label="نام و نام خانوادگی" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="username" label="نام کاربری" rules={[{ required: true, min: 3 }]}>
            <Input className="mono" disabled={!!userModal?.user} />
          </Form.Item>
          <Form.Item name="password" label={userModal?.user ? 'گذرواژه جدید (اختیاری)' : 'گذرواژه'} rules={userModal?.user ? [] : [{ required: true, min: 6 }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="mobile" label="موبایل"><Input /></Form.Item>
          <Form.Item name="role_ids" label="نقش‌ها">
            <Select mode="multiple" placeholder="انتخاب نقش" options={roles.map((r) => ({ value: r.id, label: r.title }))} />
          </Form.Item>
          <Form.Item name="is_active" label="فعال" valuePropName="checked" initialValue={true}><Switch /></Form.Item>
          <Form.Item name="is_superadmin" label="مدیر کل سامانه" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Modal>

      {/* نقش */}
      <Modal open={roleModal} title="نقش جدید" onCancel={() => setRoleModal(false)} onOk={saveRole} okText="ایجاد">
        <Form form={rForm} layout="vertical">
          <Form.Item name="title" label="عنوان نقش" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="code" label="کد (لاتین)" rules={[{ required: true, pattern: /^[a-z][a-z0-9_]*$/i }]}><Input className="mono" /></Form.Item>
          <Form.Item name="permissions" label="مجوزها">
            <Checkbox.Group
              options={perms.map((p) => ({ value: p, label: p }))}
              style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* جانشینی */}
      <Modal open={delegModal} title="ثبت جانشینی" onCancel={() => setDelegModal(false)} onOk={saveDeleg} okText="ثبت">
        <Form form={dForm} layout="vertical">
          <Form.Item name="from_user_id" label="کاربر اصلی" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label" options={users.map((u) => ({ value: u.id, label: u.full_name }))} />
          </Form.Item>
          <Form.Item name="to_user_id" label="جانشین" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label" options={users.map((u) => ({ value: u.id, label: u.full_name }))} />
          </Form.Item>
          <Form.Item name="range" label="بازه زمانی" rules={[{ required: true }]}><DatePicker.RangePicker style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="note" label="یادداشت"><Input /></Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
