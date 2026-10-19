// فهرست فرم‌ها + ایجاد فرم جدید + نسخه‌ها
import { useCallback, useEffect, useState } from 'react';
import {
  Button, Card, Empty, Form, Input, Modal, Space, Table, Tag, App as AntApp, Typography,
} from 'antd';
import { PlusOutlined, ReloadOutlined, EditOutlined, HistoryOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { api, FormRow, Paged, VersionRow, extractError } from '../api/client';

export default function FormsPage() {
  const nav = useNavigate();
  const { message, modal } = AntApp.useApp();
  const [rows, setRows] = useState<FormRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [versionsOf, setVersionsOf] = useState<FormRow | null>(null);
  const [versions, setVersions] = useState<VersionRow[]>([]);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get<Paged<FormRow>>('/forms');
      setRows(r.data.items);
    } catch (e) { message.error(extractError(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    try {
      const values = await form.validateFields();
      await api.post('/forms', values);
      message.success('فرم ایجاد شد');
      setCreateOpen(false);
      form.resetFields();
      load();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(extractError(e));
    }
  };

  const newVersion = async (f: FormRow) => {
    try {
      const latest = await api.get(`/forms/versions/${f.latest_version?.id}`);
      const r = await api.post(`/forms/${f.id}/versions`, {
        schema_json: latest.data.schema_json,
        change_note: 'نسخه جدید از آخرین نسخه',
      });
      message.success('نسخه پیش‌نویس جدید ساخته شد');
      nav(`/forms/${f.id}/design?v=${r.data.id}`);
    } catch (e) { message.error(extractError(e)); }
  };

  const showVersions = async (f: FormRow) => {
    setVersionsOf(f);
    try {
      const r = await api.get(`/forms/${f.id}`);
      setVersions(r.data.versions);
    } catch { setVersions([]); }
  };

  return (
    <Card
      title="فرم‌ها (فرم‌ساز)"
      extra={
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>فرم جدید</Button>
          <Button icon={<ReloadOutlined />} onClick={load} />
        </Space>
      }
    >
      <Table
        rowKey="id" size="small" loading={loading} dataSource={rows}
        locale={{ emptyText: <Empty description="فرمی تعریف نشده است" /> }}
        columns={[
          { title: 'عنوان', dataIndex: 'title' },
          { title: 'کلید', dataIndex: 'key', render: (v: string) => <span className="mono">{v}</span> },
          {
            title: 'نسخه منتشرشده', key: 'pub',
            render: (_: unknown, r: FormRow) => r.published_version
              ? <Tag color="success">v{r.published_version.version}</Tag>
              : <Tag color="warning">بدون انتشار</Tag>,
          },
          {
            title: 'آخرین نسخه', key: 'latest',
            render: (_: unknown, r: FormRow) => r.latest_version
              ? <Tag color={r.latest_version.status === 'draft' ? 'processing' : 'default'}>v{r.latest_version.version} ({r.latest_version.status === 'draft' ? 'پیش‌نویس' : r.latest_version.status})</Tag>
              : '—',
          },
          {
            title: 'عملیات', key: 'act',
            render: (_: unknown, r: FormRow) => (
              <Space size="small">
                <Button size="small" type="link" icon={<EditOutlined />}
                  onClick={() => nav(`/forms/${r.id}/design?v=${r.latest_version?.id || ''}`)}>طراحی</Button>
                {r.latest_version && <Button size="small" type="link" onClick={() => newVersion(r)}>نسخه جدید</Button>}
                <Button size="small" type="link" icon={<HistoryOutlined />} onClick={() => showVersions(r)}>نسخه‌ها</Button>
              </Space>
            ),
          },
        ]}
      />

      <Modal open={createOpen} title="ایجاد فرم جدید" onCancel={() => setCreateOpen(false)} onOk={create} okText="ایجاد">
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="عنوان فرم" rules={[{ required: true }]}>
            <Input placeholder="مثال: فرم مرخصی" />
          </Form.Item>
          <Form.Item name="key" label="کلید فنی (لاتین)" rules={[{ required: true, pattern: /^[a-z][a-z0-9_]*$/i, message: 'حروف لاتین، عدد و زیرخط' }]}>
            <Input placeholder="leave_request" className="mono" />
          </Form.Item>
          <Form.Item name="description" label="توضیح">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal open={!!versionsOf} title={`نسخه‌های «${versionsOf?.title}»`} onCancel={() => setVersionsOf(null)} footer={null}>
        <Table rowKey="id" size="small" pagination={false} dataSource={versions}
          columns={[
            { title: 'نسخه', dataIndex: 'version', render: (v: number) => `v${v}` },
            { title: 'وضعیت', dataIndex: 'status', render: (s: string) => <Tag color={s === 'published' ? 'success' : s === 'draft' ? 'processing' : 'default'}>{s}</Tag> },
            { title: 'توضیح تغییر', dataIndex: 'change_note' },
            {
              title: '', key: 'act',
              render: (_: unknown, v: VersionRow) => (
                <Button size="small" type="link" onClick={() => v.form_id && nav(`/forms/${v.form_id}/design?v=${v.id}`)}>مشاهده</Button>
              ),
            },
          ]} />
        <Typography.Paragraph type="secondary" style={{ marginTop: 8, fontSize: 12 }}>
          تغییر نام نمایشی فیلدها در نسخه‌های جدید، داده‌های قبلی را حفظ می‌کند (نام فنی پایدار است).
        </Typography.Paragraph>
      </Modal>
    </Card>
  );
}
