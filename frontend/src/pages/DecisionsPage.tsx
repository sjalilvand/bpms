// جدول‌های تصمیم (DMN سبک فاز ۳) — تعریف، نسخه، ویرایش گرید قواعد، انتشار و آزمون ارزیابی
import { useCallback, useEffect, useState } from 'react';
import {
  Alert, App as AntApp, Button, Card, Empty, Form, Input, InputNumber, Modal, Popconfirm,
  Select, Space, Spin, Switch, Table, Tabs, Tag, Typography,
} from 'antd';
import {
  CheckOutlined, DeleteOutlined, PlusOutlined, ReloadOutlined, SaveOutlined,
  ThunderboltOutlined, ExperimentOutlined,
} from '@ant-design/icons';
import {
  api, DecisionRow, DecisionSchemaT, DecisionInput, DecisionOutput, DecisionRule,
  extractError, Paged,
} from '../api/client';
import { useAuth } from '../auth/AuthContext';

const HIT_POLICIES: { value: DecisionSchemaT['hitPolicy']; label: string; hint: string }[] = [
  { value: 'FIRST', label: 'اولین قاعده منطبق (FIRST)', hint: 'نخستین قاعده منطبق بر اساس ترتیب اجرا می‌شود' },
  { value: 'UNIQUE', label: 'یکتا (UNIQUE)', hint: 'باید فقط یک قاعده منطبق شود؛ تضاد = خطا' },
  { value: 'ANY', label: 'هم‌خوان (ANY)', hint: 'خروجی قواعد منطبق باید یکسان باشد' },
  { value: 'PRIORITY', label: 'اولویت‌دار (PRIORITY)', hint: 'قاعده با کمترین شماره اولویت انتخاب می‌شود' },
  { value: 'COLLECT', label: 'تجمعی (COLLECT)', hint: 'همه قواعد منطبق به‌صورت فهرست برگردانده می‌شوند' },
];

function emptySchema(): DecisionSchemaT {
  return {
    hitPolicy: 'FIRST',
    inputs: [{ name: 'amount', label: 'مبلغ', type: 'number' }],
    outputs: [{ name: 'result', label: 'نتیجه' }],
    rules: [],
  };
}

export default function DecisionsPage() {
  const { message } = AntApp.useApp();
  const { user, hasPerm } = useAuth();
  const canManage = user?.is_superadmin || hasPerm('decision.manage');

  const [rows, setRows] = useState<DecisionRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();

  const [editorId, setEditorId] = useState<number | null>(null);
  const [editor, setEditor] = useState<{
    def: DecisionRow | null; versionId: number; version: number; status: string;
    schema: DecisionSchemaT; changeNote: string;
  } | null>(null);
  const [saving, setSaving] = useState(false);
  const [testOpen, setTestOpen] = useState(false);
  const [testInputs, setTestInputs] = useState('');
  const [testResult, setTestResult] = useState<string>('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get<Paged<DecisionRow>>('/decisions');
      setRows(r.data.items);
    } catch (e) { message.error(extractError(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    try {
      const v = await createForm.validateFields();
      const r = await api.post('/decisions', v);
      message.success('جدول تصمیم ایجاد شد');
      setCreateOpen(false);
      createForm.resetFields();
      await load();
      openEditor(r.data.id);
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(extractError(e));
    }
  };

  const openEditor = async (id: number, versionId?: number) => {
    try {
      const d = await api.get(`/decisions/${id}`);
      const vid = versionId || d.data.latest_published?.id || d.data.versions?.[0]?.id;
      if (!vid) {
        // نسخه‌ای ندارد — ویرایشگر با اسکلت خالی
        setEditor({ def: d.data, versionId: 0, version: 0, status: 'none', schema: emptySchema(), changeNote: '' });
        setEditorId(id);
        return;
      }
      const v = await api.get(`/decisions/versions/${vid}`);
      setEditor({
        def: d.data, versionId: v.data.id, version: v.data.version, status: v.data.status,
        schema: { ...emptySchema(), ...(v.data.schema_json || {}) }, changeNote: v.data.change_note || '',
      });
      setEditorId(id);
    } catch (e) { message.error(extractError(e)); }
  };

  const saveVersion = async (publish: boolean) => {
    if (!editor) return;
    setSaving(true);
    try {
      const schemaJson = JSON.stringify(editor.schema);
      if (editor.versionId) {
        await api.put(`/decisions/versions/${editor.versionId}`, {
          schema_json: JSON.parse(schemaJson), change_note: editor.changeNote,
        });
        if (publish) {
          await api.post(`/decisions/versions/${editor.versionId}/publish`);
          message.success('نسخه جدول تصمیم منتشر شد');
        } else {
          message.success('پیش‌نویس ذخیره شد');
        }
      } else {
        const r = await api.post(`/decisions/${editorId}/versions`, {
          schema_json: JSON.parse(schemaJson), change_note: editor.changeNote || 'نسخه اولیه',
        });
        if (publish) await api.post(`/decisions/versions/${r.data.id}/publish`);
        message.success(publish ? 'نسخه اول منتشر شد' : 'نسخه اول ذخیره شد');
      }
      await load();
      openEditor(editorId!, editor?.versionId || undefined);
    } catch (e: any) {
      const resp = e?.response?.data?.error;
      if (resp?.errors) message.error({ content: resp.errors.map((x: any) => x.message).join(' | '), duration: 8 });
      else message.error(extractError(e));
    } finally { setSaving(false); }
  };

  const runTest = async () => {
    try {
      const data = JSON.parse(testInputs || '{}');
      const r = await api.post(`/decisions/${editorId}/evaluate`, { data });
      setTestResult(JSON.stringify(r.data.result, null, 2));
    } catch (e: any) {
      if (e instanceof SyntaxError) { setTestResult('JSON نامعتبر است'); return; }
      setTestResult('خطا: ' + extractError(e));
    }
  };

  // ---------- ویرایش schema ----------
  const patchSchema = (patch: Partial<DecisionSchemaT>) => {
    if (!editor) return;
    setEditor({ ...editor, schema: { ...editor.schema, ...patch } });
  };

  const addInput = () => patchSchema({ inputs: [...editor!.schema.inputs, { name: `input${editor!.schema.inputs.length + 1}`, label: 'ورودی جدید', type: 'string' }] });
  const addOutput = () => patchSchema({ outputs: [...editor!.schema.outputs, { name: `output${editor!.schema.outputs.length + 1}`, label: 'خروجی جدید' }] });
  const addRule = () => {
    const ie: Record<string, string> = {};
    editor!.schema.inputs.forEach((i) => { ie[i.name] = ''; });
    const oe: Record<string, unknown> = {};
    editor!.schema.outputs.forEach((o) => { oe[o.name] = ''; });
    patchSchema({
      rules: [...editor!.schema.rules, {
        id: `r${editor!.schema.rules.length + 1}`, inputEntries: ie, outputEntries: oe,
        priority: editor!.schema.rules.length + 1, enabled: true,
      }],
    });
  };

  const patchRule = (idx: number, patch: Partial<DecisionRule>) => {
    const rules = editor!.schema.rules.map((r, i) => (i === idx ? { ...r, ...patch } : r));
    patchSchema({ rules });
  };

  const patchEntry = (idx: number, kind: 'in' | 'out', key: string, value: string) => {
    const rule = editor!.schema.rules[idx];
    if (kind === 'in') {
      patchRule(idx, { inputEntries: { ...rule.inputEntries, [key]: value } });
    } else {
      patchRule(idx, { outputEntries: { ...rule.outputEntries, [key]: value } });
    }
  };

  const removeRule = (idx: number) => patchSchema({ rules: editor!.schema.rules.filter((_, i) => i !== idx) });

  const patchColDef = (kind: 'inputs' | 'outputs', idx: number, patch: Partial<DecisionInput & DecisionOutput>) => {
    const arr = editor!.schema[kind].map((c, i) => (i === idx ? { ...c, ...patch } : c));
    patchSchema({ [kind]: arr } as Partial<DecisionSchemaT>);
  };

  const removeCol = (kind: 'inputs' | 'outputs', idx: number) => {
    const arr = editor!.schema[kind].filter((_, i) => i !== idx);
    patchSchema({ [kind]: arr } as Partial<DecisionSchemaT>);
  };

  const columns: any[] = [];
  if (editor) {
    columns.push({
      title: '#', key: 'idx', width: 44,
      render: (_: unknown, __: unknown, i: number) => <Typography.Text type="secondary">{i + 1}</Typography.Text>,
    });
    editor.schema.inputs.forEach((inp, ci) => {
      columns.push({
        title: (
          <Space size={4}>
            <Typography.Text strong>{inp.label || inp.name}</Typography.Text>
            {canManage && (
              <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={() => removeCol('inputs', ci)} />
            )}
          </Space>
        ),
        key: `in-${inp.name}`,
        width: 190,
        onHeaderCell: () => ({ style: { background: '#f0f7ff' } }),
        render: (_: unknown, rule: DecisionRule, ri: number) => (
          <Input size="small" className="mono" placeholder="- (هر مقدار)"
            value={rule.inputEntries?.[inp.name] ?? ''}
            onChange={(e) => patchEntry(ri, 'in', inp.name, e.target.value)} />
        ),
      });
    });
    editor.schema.outputs.forEach((out, ci) => {
      columns.push({
        title: (
          <Space size={4}>
            <Typography.Text strong style={{ color: '#1677ff' }}>{out.label || out.name}</Typography.Text>
            {canManage && (
              <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={() => removeCol('outputs', ci)} />
            )}
          </Space>
        ),
        key: `out-${out.name}`,
        width: 190,
        onHeaderCell: () => ({ style: { background: '#f0f7ff' } }),
        render: (_: unknown, rule: DecisionRule, ri: number) => (
          <Input size="small" className="mono"
            value={String(rule.outputEntries?.[out.name] ?? '')}
            onChange={(e) => patchEntry(ri, 'out', out.name, e.target.value)} />
        ),
      });
    });
    if (editor.schema.hitPolicy === 'PRIORITY') {
      columns.push({
        title: 'اولویت', key: 'priority', width: 90,
        render: (_: unknown, rule: DecisionRule, ri: number) => (
          <InputNumber size="small" min={1} value={rule.priority} onChange={(v) => patchRule(ri, { priority: v || 1 })} />
        ),
      });
    }
    columns.push({
      title: 'فعال', key: 'enabled', width: 70,
      render: (_: unknown, rule: DecisionRule, ri: number) => (
        <Switch size="small" checked={rule.enabled !== false} onChange={(v) => patchRule(ri, { enabled: v })} />
      ),
    });
    if (canManage) {
      columns.push({
        title: '', key: 'del', width: 50,
        render: (_: unknown, __: unknown, ri: number) => (
          <Popconfirm title="حذف قاعده؟" onConfirm={() => removeRule(ri)}>
            <Button size="small" type="text" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        ),
      });
    }
  }

  const policyHint = editor ? HIT_POLICIES.find((p) => p.value === editor.schema.hitPolicy)?.hint : '';

  return (
    <div>
      <Card
        title="جدول‌های تصمیم (DMN سبک)"
        extra={canManage && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>جدول جدید</Button>
        )}
      >
        <Table<DecisionRow>
          rowKey="id" loading={loading} dataSource={rows}
          pagination={false}
          locale={{ emptyText: <Empty description="هنوز جدول تصمیمی تعریف نشده است" /> }}
          columns={[
            { title: 'کلید', dataIndex: 'key', key: 'key', width: 180, render: (k: string) => <Typography.Text code>{k}</Typography.Text> },
            { title: 'عنوان', dataIndex: 'title', key: 'title' },
            {
              title: 'وضعیت', key: 'status', width: 130,
              render: (_: unknown, r: DecisionRow) => r.latest_published
                ? <Tag color="green">منتشرشده v{r.latest_published.version}</Tag>
                : <Tag color="orange">بدون نسخه منتشرشده</Tag>,
            },
            {
              title: 'عملیات', key: 'act', width: 260,
              render: (_: unknown, r: DecisionRow) => (
                <Space>
                  <Button size="small" icon={<ThunderboltOutlined />} onClick={() => openEditor(r.id)}>ویرایش</Button>
                  {r.latest_published && (
                    <Button size="small" icon={<ExperimentOutlined />}
                      onClick={async () => { await openEditor(r.id, r.latest_published!.id); setTestOpen(true); setTestInputs('{\n  "amount": 100\n}'); setTestResult(''); }}>
                        آزمون
                    </Button>
                  )}
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal open={createOpen} title="جدول تصمیم جدید" onOk={create} onCancel={() => setCreateOpen(false)} okText="ایجاد">
        <Form form={createForm} layout="vertical">
          <Form.Item name="key" label="کلید (لاتین)" rules={[
            { required: true, message: 'کلید الزامی است' },
            { pattern: /^[a-z][a-z0-9_]*$/, message: 'فقط حروف کوچک، رقم و زیرخط' },
          ]}>
            <Input placeholder="purchase_approval" className="mono" />
          </Form.Item>
          <Form.Item name="title" label="عنوان" rules={[{ required: true, message: 'عنوان الزامی است' }]}>
            <Input placeholder="سطح‌بندی تأیید خرید" />
          </Form.Item>
          <Form.Item name="description" label="توضیح"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      {editor && (
        <Card
          style={{ marginTop: 16 }}
          title={
            <Space wrap>
              <span>ویرایش جدول تصمیم: {editor.def?.title}</span>
              {editor.status === 'published' && <Tag color="green">نسخه v{editor.version} منتشرشده</Tag>}
              {editor.status === 'draft' && <Tag color="orange">نسخه v{editor.version} پیش‌نویس</Tag>}
              {editor.status === 'none' && <Tag color="red">بدون نسخه</Tag>}
            </Space>
          }
          extra={
            <Space wrap>
              <Button icon={<ExperimentOutlined />} onClick={() => { setTestOpen(true); setTestInputs('{\n}'); setTestResult(''); }}>آزمون ارزیابی</Button>
              {editor.status === 'published' && (
                <Button icon={<PlusOutlined />} onClick={async () => {
                  try {
                    const r = await api.post(`/decisions/${editorId}/versions`, {
                      schema_json: editor.schema, change_note: 'نسخه جدید از مدل جاری',
                    });
                    message.success('نسخه پیش‌نویس جدید ساخته شد');
                    await load();
                    openEditor(editorId!, r.data.id);
                  } catch (e) { message.error(extractError(e)); }
                }}>نسخه جدید</Button>
              )}
              {canManage && editor.status !== 'published' && (
                <>
                  <Button icon={<SaveOutlined />} loading={saving} onClick={() => saveVersion(false)}>ذخیره پیش‌نویس</Button>
                  <Button type="primary" icon={<CheckOutlined />} loading={saving} onClick={() => saveVersion(true)}>انتشار</Button>
                </>
              )}
              <Button icon={<ReloadOutlined />} onClick={() => openEditor(editorId!)}>بازآوری</Button>
            </Space>
          }
        >
          {editor.status === 'published' && (
            <Alert style={{ marginBottom: 12 }} type="info" showIcon
              message="این نسخه منتشرشده و تغییرناپذیر است (قرارداد نسخه‌بندی). برای ویرایش، «نسخه جدید» بسازید." />
          )}
          <Tabs
            items={[
              {
                key: 'rules', label: 'قواعد تصمیم',
                children: (
                  <div>
                    <Space style={{ marginBottom: 12 }} wrap>
                      <span>سیاست برخورد:</span>
                      <Select style={{ minWidth: 260 }} value={editor.schema.hitPolicy}
                        disabled={!canManage || editor.status === 'published'}
                        onChange={(v) => patchSchema({ hitPolicy: v })}
                        options={HIT_POLICIES.map((p) => ({ value: p.value, label: p.label }))} />
                      <Typography.Text type="secondary">{policyHint}</Typography.Text>
                    </Space>
                    <Space style={{ marginBottom: 8 }} wrap>
                      {canManage && editor.status !== 'published' && (
                        <>
                          <Button size="small" icon={<PlusOutlined />} onClick={addInput}>ورودی</Button>
                          <Button size="small" icon={<PlusOutlined />} onClick={addOutput}>خروجی</Button>
                          <Button size="small" type="primary" ghost icon={<PlusOutlined />} onClick={addRule}>قاعده</Button>
                        </>
                      )}
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        نمونه عبارت ورودی: <code>&gt; 100</code> ، <code>between 10..20</code> ، <code>in a,b</code> ، <code>== 'x'</code> ، خالی = هر مقدار
                      </Typography.Text>
                    </Space>
                    <Table
                      size="small" rowKey={(_r, i) => String(i)}
                      dataSource={editor.schema.rules} columns={columns} pagination={false}
                      locale={{ emptyText: 'قاعده‌ای تعریف نشده است' }}
                      scroll={{ x: 'max-content' }}
                    />
                  </div>
                ),
              },
              {
                key: 'cols', label: 'ستون‌ها',
                children: (
                  <div>
                    <Typography.Title level={5}>ورودی‌ها</Typography.Title>
                    <Table
                      size="small" rowKey={(_r, i) => `i${i}`} pagination={false}
                      dataSource={editor.schema.inputs}
                      columns={[
                        { title: 'نام', key: 'n', render: (_: unknown, c: DecisionInput, i: number) => <Input size="small" className="mono" value={c.name} onChange={(e) => patchColDef('inputs', i, { name: e.target.value })} /> },
                        { title: 'عنوان', key: 'l', render: (_: unknown, c: DecisionInput, i: number) => <Input size="small" value={c.label} onChange={(e) => patchColDef('inputs', i, { label: e.target.value })} /> },
                        { title: 'نوع', key: 't', width: 130, render: (_: unknown, c: DecisionInput, i: number) => (
                          <Select size="small" value={c.type || 'string'} onChange={(v) => patchColDef('inputs', i, { type: v })}
                            options={[{ value: 'number', label: 'عدد' }, { value: 'string', label: 'متن' }, { value: 'boolean', label: 'بله/خیر' }]} />
                        ) },
                        { title: '', key: 'x', width: 50, render: (_: unknown, __: unknown, i: number) => (
                          <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={() => removeCol('inputs', i)} />
                        ) },
                      ]}
                    />
                    <Typography.Title level={5} style={{ marginTop: 16 }}>خروجی‌ها</Typography.Title>
                    <Table
                      size="small" rowKey={(_r, i) => `o${i}`} pagination={false}
                      dataSource={editor.schema.outputs}
                      columns={[
                        { title: 'نام', key: 'n', render: (_: unknown, c: DecisionOutput, i: number) => <Input size="small" className="mono" value={c.name} onChange={(e) => patchColDef('outputs', i, { name: e.target.value })} /> },
                        { title: 'عنوان', key: 'l', render: (_: unknown, c: DecisionOutput, i: number) => <Input size="small" value={c.label} onChange={(e) => patchColDef('outputs', i, { label: e.target.value })} /> },
                        { title: 'مقدار پیش‌فرض', key: 'd', width: 160, render: (_: unknown, c: DecisionOutput, i: number) => <Input size="small" className="mono" value={String(c.defaultValue ?? '')} onChange={(e) => patchColDef('outputs', i, { defaultValue: e.target.value })} /> },
                        { title: '', key: 'x', width: 50, render: (_: unknown, __: unknown, i: number) => (
                          <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={() => removeCol('outputs', i)} />
                        ) },
                      ]}
                    />
                  </div>
                ),
              },
              {
                key: 'test', label: 'آزمون',
                children: (
                  <div style={{ maxWidth: 640 }}>
                    <Typography.Paragraph type="secondary">داده ورودی (JSON) را وارد کنید و ارزیابی را اجرا کنید.</Typography.Paragraph>
                    <Input.TextArea className="mono" rows={5} value={testInputs} onChange={(e) => setTestInputs(e.target.value)} />
                    <Button style={{ marginBlock: 10 }} icon={<ExperimentOutlined />} onClick={runTest}>ارزیابی</Button>
                    {testResult && (
                      <Alert type={testResult.startsWith('خطا') || testResult.includes('نامعتبر') ? 'error' : 'success'}
                        message={<pre className="mono" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{testResult}</pre>} />
                    )}
                  </div>
                ),
              },
            ]}
          />
        </Card>
      )}

      {!editor && rows.length === 0 && !loading && (
        <Empty style={{ marginTop: 40 }} description="برای شروع، یک جدول تصمیم ایجاد کنید" />
      )}
      {!editor && rows.length > 0 && (
        <Alert style={{ marginTop: 16 }} type="info" message="برای ویرایش، یک جدول را انتخاب کنید" />
      )}
      {editor === null && loading && <Spin style={{ display: 'block', margin: '40px auto' }} />}
    </div>
  );
}
