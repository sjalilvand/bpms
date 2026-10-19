// فهرست فرایندها + شروع درخواست با فرم شروع
import { useCallback, useEffect, useState } from 'react';
import { Button, Card, Drawer, Modal, Form, Input, Space, Table, Tag, App as AntApp, Typography } from 'antd';
import { PlusOutlined, ReloadOutlined, EditOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { api, ProcessRow, Paged, extractError } from '../api/client';
import FormRenderer from '../components/FormRenderer';
import type { FormSchema } from '../lib/formSchema';
import { useAuth } from '../auth/AuthContext';

export default function ProcessesPage() {
  const nav = useNavigate();
  const { user, hasPerm } = useAuth();
  const { message } = AntApp.useApp();
  const [rows, setRows] = useState<ProcessRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm();

  // شروع درخواست
  const [startOf, setStartOf] = useState<ProcessRow | null>(null);
  const [startSchema, setStartSchema] = useState<FormSchema | null>(null);
  const [starting, setStarting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get<Paged<ProcessRow>>('/processes');
      setRows(r.data.items);
    } catch (e) { message.error(extractError(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openStart = async (p: ProcessRow) => {
    setStartOf(p);
    setStartSchema(null);
    try {
      const ver = await api.get(`/processes/versions/${p.published_version?.id}`);
      const startBinding = ver.data.config_json?.bindings?.start;
      if (startBinding?.formDefinitionId) {
        const f = await api.get(`/forms/versions/published-by-form/${startBinding.formDefinitionId}`);
        setStartSchema(f.data.schema_json);
      }
    } catch { setStartSchema(null); }
  };

  const start = async (values: Record<string, unknown>) => {
    if (!startOf) return;
    setStarting(true);
    try {
      const r = await api.post('/process-instances', {
        definition_id: startOf.id,
        data: values,
      });
      message.success(`درخواست با شناسه #${r.data.id} ثبت شد`);
      setStartOf(null);
      nav(`/instances/${r.data.id}`);
    } catch (e) {
      message.error({ content: extractError(e), duration: 8 });
    } finally { setStarting(false); }
  };

  const createProcess = async () => {
    try {
      const values = await form.validateFields();
      await api.post('/processes', values);
      message.success('فرایند ایجاد شد؛ اکنون مدل BPMN را در طراح بارگذاری کنید');
      setCreateOpen(false);
      form.resetFields();
      load();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(extractError(e));
    }
  };

  return (
    <Card
      title="فرایندها"
      extra={
        <Space>
          {hasPerm('process.manage') && <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>فرایند جدید</Button>}
          <Button icon={<ReloadOutlined />} onClick={load} />
        </Space>
      }
    >
      <Table
        rowKey="id" size="small" loading={loading} dataSource={rows}
        columns={[
          { title: 'عنوان', dataIndex: 'title' },
          { title: 'کلید', dataIndex: 'key', render: (v: string) => <span className="mono">{v}</span> },
          {
            title: 'نسخه منتشرشده', key: 'pub',
            render: (_: unknown, r: ProcessRow) => r.published_version
              ? <Tag color="success">v{r.published_version.version}</Tag>
              : <Tag color="warning">بدون انتشار</Tag>,
          },
          {
            title: 'عملیات', key: 'act',
            render: (_: unknown, r: ProcessRow) => (
              <Space size="small">
                {r.published_version && hasPerm('process.start') && (
                  <Button size="small" type="primary" onClick={() => openStart(r)}>ثبت درخواست</Button>
                )}
                {hasPerm('process.manage') && (
                  <Button size="small" type="link" icon={<EditOutlined />}
                    onClick={() => nav(`/processes/${r.id}/design?v=${r.latest_version?.id || ''}`)}>طراحی</Button>
                )}
              </Space>
            ),
          },
        ]}
      />

      <Modal open={createOpen} title="ایجاد فرایند جدید" onCancel={() => setCreateOpen(false)} onOk={createProcess} okText="ایجاد">
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="عنوان فرایند" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="key" label="کلید فنی (لاتین)" rules={[{ required: true, pattern: /^[a-z][a-z0-9_]*$/i }]}><Input className="mono" /></Form.Item>
          <Form.Item name="description" label="توضیح"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      <Drawer
        open={!!startOf} onClose={() => setStartOf(null)} width={760}
        title={`ثبت درخواست: ${startOf?.title || ''}`}
        destroyOnClose
      >
        {startSchema ? (
          <FormRenderer schema={startSchema} submitting={starting} submitText="ثبت درخواست" onFinish={start} />
        ) : (
          <Typography.Text type="warning">
            این فرایند فرم شروع منتشرشده ندارد؛ ابتدا در تنظیمات فعالیت «start» فرم را متصل کنید و نسخه را منتشر نمایید.
          </Typography.Text>
        )}
      </Drawer>
    </Card>
  );
}
