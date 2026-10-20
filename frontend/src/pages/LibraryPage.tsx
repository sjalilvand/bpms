// بانک سازمانی — فیلدهای سازمانی / بانک فرم‌ها / بانک فرایندها (فاز ۸)
import { useCallback, useEffect, useState } from 'react';
import {
  Button, Card, Empty, Form, Input, Modal, Select, Space, Table, Tag, Tabs, App as AntApp, Typography, Popconfirm,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, CopyOutlined, DeleteOutlined, DatabaseOutlined, EditOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { api, extractError } from '../api/client';
import { FIELD_TYPES } from '../lib/formSchema';

const { Text } = Typography;

interface OrgFieldRow {
  id: number; key: string; label: string; type: string; category: string; description: string;
  config_json: Record<string, unknown>;
}
interface FormTplRow {
  id: number; key: string; title: string; description: string; category: string;
  field_count: number; fields_preview: { key: string; label: string; type: string }[];
}
interface ProcTplRow {
  id: number; key: string; title: string; description: string; category: string;
  main_process_id: string; has_bindings: boolean;
}

const TYPE_OPTIONS = Object.entries(FIELD_TYPES).map(([k, v]) => ({ value: k, label: `${v.label} (${k})` }));

export default function LibraryPage() {
  const nav = useNavigate();
  const { message } = AntApp.useApp();
  const [tab, setTab] = useState('fields');

  // ---------- فیلدهای سازمانی ----------
  const [fields, setFields] = useState<OrgFieldRow[]>([]);
  const [fieldModal, setFieldModal] = useState<{ open: boolean; row: OrgFieldRow | null }>({ open: false, row: null });
  const [fieldForm] = Form.useForm();

  // ---------- بانک فرم‌ها ----------
  const [formTpls, setFormTpls] = useState<FormTplRow[]>([]);
  const [instantiateForm, setInstantiateForm] = useState<FormTplRow | null>(null);
  const [instForm] = Form.useForm();

  // ---------- بانک فرایندها ----------
  const [procTpls, setProcTpls] = useState<ProcTplRow[]>([]);
  const [instantiateProc, setInstantiateProc] = useState<ProcTplRow | null>(null);
  const [instProc] = Form.useForm();

  const load = useCallback(async () => {
    try {
      const [f, ft, pt] = await Promise.all([
        api.get('/library/fields'),
        api.get('/library/forms'),
        api.get('/library/processes'),
      ]);
      setFields(f.data.items || []);
      setFormTpls(ft.data.items || []);
      setProcTpls(pt.data.items || []);
    } catch (e) { message.error(extractError(e)); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const saveField = async () => {
    try {
      const v = await fieldForm.validateFields();
      if (fieldModal.row) await api.put(`/library/fields/${fieldModal.row.id}`, v);
      else await api.post('/library/fields', v);
      message.success(fieldModal.row ? 'فیلد سازمانی ویرایش شد' : 'فیلد سازمانی ثبت شد — اکنون در فرم‌ساز قابل استفاده است');
      setFieldModal({ open: false, row: null });
      fieldForm.resetFields();
      load();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(extractError(e));
    }
  };

  const instantiateFormTpl = async () => {
    if (!instantiateForm) return;
    try {
      const v = await instForm.validateFields();
      const r = await api.post(`/library/forms/${instantiateForm.id}/instantiate`, v);
      message.success('فرم جدید از الگو ساخته شد — به فرم‌ساز منتقل می‌شوید');
      setInstantiateForm(null);
      instForm.resetFields();
      nav(`/forms/${r.data.id}/design?v=${r.data.version_id}`);
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(extractError(e));
    }
  };

  const instantiateProcTpl = async () => {
    if (!instantiateProc) return;
    try {
      const v = await instProc.validateFields();
      const r = await api.post(`/library/processes/${instantiateProc.id}/instantiate`, v);
      message.success('فرایند جدید از الگو ساخته شد (پیش‌نویس) — به طراح منتقل می‌شوید');
      setInstantiateProc(null);
      instProc.resetFields();
      nav(`/processes/${r.data.id}/design?v=${r.data.version_id}`);
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(extractError(e));
    }
  };

  const fieldColumns = [
    { title: 'کلید', dataIndex: 'key', width: 180, render: (v: string) => <Text code className="mono">{v}</Text> },
    { title: 'برچسب', dataIndex: 'label', width: 180 },
    { title: 'نوع', dataIndex: 'type', width: 140, render: (t: string) => <Tag>{FIELD_TYPES[t]?.label || t}</Tag> },
    { title: 'دسته', dataIndex: 'category', width: 120, render: (v: string) => v || '—' },
    {
      title: 'تنظیمات', dataIndex: 'config_json', render: (c: Record<string, unknown>) => {
        const parts: string[] = [];
        if (c?.required) parts.push('الزامی');
        if (c?.help) parts.push(String(c.help).slice(0, 40));
        if (c?.moneyUnit) parts.push(String(c.moneyUnit));
        return parts.join('، ') || '—';
      },
    },
    {
      title: 'عملیات', width: 100,
      render: (_: unknown, r: OrgFieldRow) => (
        <Space size={0}>
          <Button type="text" size="small" icon={<EditOutlined />}
            onClick={() => { setFieldModal({ open: true, row: r }); fieldForm.setFieldsValue(r); }} />
          <Popconfirm title="حذف فیلد سازمانی؟" onConfirm={async () => {
            try { await api.delete(`/library/fields/${r.id}`); message.success('حذف شد'); load(); }
            catch (e) { message.error(extractError(e)); }
          }}>
            <Button type="text" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const formTplColumns = [
    { title: 'کلید', dataIndex: 'key', width: 180, render: (v: string) => <Text code className="mono">{v}</Text> },
    { title: 'عنوان', dataIndex: 'title', width: 200 },
    { title: 'دسته', dataIndex: 'category', width: 120, render: (v: string) => v || '—' },
    { title: 'تعداد فیلد', dataIndex: 'field_count', width: 90, align: 'center' as const },
    {
      title: 'فیلدها', dataIndex: 'fields_preview',
      render: (fs: FormTplRow['fields_preview']) => (
        <Space size={[4, 4]} wrap>
          {fs.map((f) => <Tag key={f.key || f.label}>{f.label} <Text type="secondary" style={{ fontSize: 10 }}>{FIELD_TYPES[f.type]?.label}</Text></Tag>)}
        </Space>
      ),
    },
    {
      title: 'عملیات', width: 140,
      render: (_: unknown, r: FormTplRow) => (
        <Space size={4}>
          <Button size="small" type="primary" icon={<CopyOutlined />} onClick={() => {
            setInstantiateForm(r);
            instForm.setFieldsValue({ key: `${r.key}_new`, title: r.title });
          }}>ساخت فرم</Button>
          <Popconfirm title="حذف الگو از بانک؟" onConfirm={async () => {
            try { await api.delete(`/library/forms/${r.id}`); message.success('حذف شد'); load(); }
            catch (e) { message.error(extractError(e)); }
          }}>
            <Button type="text" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const procTplColumns = [
    { title: 'کلید', dataIndex: 'key', width: 180, render: (v: string) => <Text code className="mono">{v}</Text> },
    { title: 'عنوان', dataIndex: 'title', width: 200 },
    { title: 'دسته', dataIndex: 'category', width: 120, render: (v: string) => v || '—' },
    {
      title: 'اتصالات', dataIndex: 'has_bindings', width: 110,
      render: (v: boolean) => v ? <Tag color="green">فرم/مسئول تنظیم‌شده</Tag> : <Tag>فقط مدل</Tag>,
    },
    { title: 'فرایند اصلی', dataIndex: 'main_process_id', render: (v: string) => <Text code className="mono" style={{ fontSize: 11 }}>{v || '—'}</Text> },
    {
      title: 'عملیات', width: 150,
      render: (_: unknown, r: ProcTplRow) => (
        <Space size={4}>
          <Button size="small" type="primary" icon={<CopyOutlined />} onClick={() => {
            setInstantiateProc(r);
            instProc.setFieldsValue({ key: `${r.key}_new`, title: r.title });
          }}>ساخت فرایند</Button>
          <Popconfirm title="حذف الگو از بانک؟" onConfirm={async () => {
            try { await api.delete(`/library/processes/${r.id}`); message.success('حذف شد'); load(); }
            catch (e) { message.error(extractError(e)); }
          }}>
            <Button type="text" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title={<span><DatabaseOutlined /> بانک سازمانی — فیلدها، فرم‌ها و فرایندهای الگو</span>}
      extra={<Button icon={<ReloadOutlined />} onClick={load}>بازخوانی</Button>}
    >
      <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
        الگوها و فیلدهای استاندارد سازمان اینجا نگهداری می‌شوند. فیلدهای سازمانی در فرم‌ساز کنار اجزای پایه ظاهر می‌شوند؛
        فرم‌ها و فرایندهای موجود را می‌توانید از صفحات مربوطه «در بانک ذخیره» کنید تا برای همه قابل استفاده باشد.
      </Typography.Paragraph>
      <Tabs
        activeKey={tab} onChange={setTab}
        items={[
          {
            key: 'fields', label: `فیلدهای سازمانی (${fields.length})`,
            children: (
              <>
                <Space style={{ marginBottom: 12 }}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => {
                    setFieldModal({ open: true, row: null });
                    fieldForm.resetFields();
                  }}>ثبت فیلد سازمانی</Button>
                </Space>
                <Table
                  rowKey="id" size="small" columns={fieldColumns} dataSource={fields}
                  locale={{ emptyText: <Empty description="فیلد سازمانی ثبت نشده است" /> }}
                  pagination={{ pageSize: 10 }}
                />
              </>
            ),
          },
          {
            key: 'forms', label: `بانک فرم‌ها (${formTpls.length})`,
            children: (
              <Table
                rowKey="id" size="small" columns={formTplColumns} dataSource={formTpls}
                locale={{ emptyText: <Empty description="الگویی در بانک فرم‌ها نیست — از صفحه فرم‌ها فرم را در بانک ذخیره کنید" /> }}
                pagination={{ pageSize: 10 }}
              />
            ),
          },
          {
            key: 'processes', label: `بانک فرایندها (${procTpls.length})`,
            children: (
              <Table
                rowKey="id" size="small" columns={procTplColumns} dataSource={procTpls}
                locale={{ emptyText: <Empty description="الگویی در بانک فرایندها نیست — از طراح فرایند، مدل را در بانک ذخیره کنید" /> }}
                pagination={{ pageSize: 10 }}
              />
            ),
          },
        ]}
      />

      {/* مودال فیلد سازمانی */}
      <Modal
        open={fieldModal.open}
        title={fieldModal.row ? 'ویرایش فیلد سازمانی' : 'ثبت فیلد سازمانی جدید'}
        onCancel={() => setFieldModal({ open: false, row: null })}
        onOk={saveField}
        okText="ذخیره"
      >
        <Form form={fieldForm} layout="vertical" size="small">
          <Form.Item name="key" label="کلید فنی (پایدار در داده‌ها)" rules={[
            { required: true }, { pattern: /^[a-z][a-z0-9_]*$/i, message: 'فقط حروف لاتین، عدد و زیرخط' }]}>
            <Input className="mono" placeholder="مثال: employee_code" />
          </Form.Item>
          <Form.Item name="label" label="برچسب" rules={[{ required: true }]}>
            <Input placeholder="مثال: کد پرسنلی" />
          </Form.Item>
          <Form.Item name="type" label="نوع جزء" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label" options={TYPE_OPTIONS} placeholder="انتخاب نوع" />
          </Form.Item>
          <Form.Item name="category" label="دسته (مثال: پرسنلی، مالی)">
            <Input />
          </Form.Item>
          <Form.Item name={['config_json', 'required']} label="الزامی پیش‌فرض" valuePropName="checked">
            <Select options={[{ value: true, label: 'الزامی' }, { value: false, label: 'اختیاری' }]} allowClear placeholder="اختیاری" />
          </Form.Item>
          <Form.Item name={['config_json', 'help']} label="متن راهنما">
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      {/* ساخت فرم از الگو */}
      <Modal
        open={!!instantiateForm}
        title={`ساخت فرم جدید از الگوی «${instantiateForm?.title || ''}»`}
        onCancel={() => setInstantiateForm(null)}
        onOk={instantiateFormTpl}
        okText="ساخت فرم"
      >
        <Form form={instForm} layout="vertical" size="small">
          <Form.Item name="key" label="کلید فرم جدید" rules={[{ required: true }]}>
            <Input className="mono" />
          </Form.Item>
          <Form.Item name="title" label="عنوان فرم جدید" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Text type="secondary" style={{ fontSize: 12 }}>
            یک نسخه پیش‌نویس با همه فیلدهای الگو ساخته می‌شود؛ در فرم‌ساز قابل ویرایش است.
          </Text>
        </Form>
      </Modal>

      {/* ساخت فرایند از الگو */}
      <Modal
        open={!!instantiateProc}
        title={`ساخت فرایند جدید از الگوی «${instantiateProc?.title || ''}»`}
        onCancel={() => setInstantiateProc(null)}
        onOk={instantiateProcTpl}
        okText="ساخت فرایند"
      >
        <Form form={instProc} layout="vertical" size="small">
          <Form.Item name="key" label="کلید فرایند جدید" rules={[{ required: true }]}>
            <Input className="mono" />
          </Form.Item>
          <Form.Item name="title" label="عنوان فرایند جدید" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Text type="secondary" style={{ fontSize: 12 }}>
            نسخه اول پیش‌نویس با BPMN و اتصالات فرم/مسئول الگو ساخته می‌شود؛ در طراح قابل اصلاح و انتشار است.
          </Text>
        </Form>
      </Modal>
    </Card>
  );
}
