// ساختار سازمانی سلسله‌مراتبی
import { useCallback, useEffect, useState } from 'react';
import { Button, Card, Col, Form, Input, Modal, Popconfirm, Row, Space, Tree, App as AntApp, Typography } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import type { DataNode } from 'antd/es/tree';
import { api, extractError } from '../api/client';

interface Unit { id: number; name: string; code: string | null; parent_id: number | null; children?: Unit[] }

function toTree(items: Unit[]): DataNode[] {
  return items.map((u) => ({
    key: u.id,
    title: `${u.name}${u.code ? ` (${u.code})` : ''}`,
    children: u.children?.length ? toTree(u.children) : undefined,
  }));
}

export default function OrgPage() {
  const { message } = AntApp.useApp();
  const [tree, setTree] = useState<Unit[]>([]);
  const [selected, setSelected] = useState<Unit | null>(null);
  const [modal, setModal] = useState<null | { parent_id: number | null; unit?: Unit }>(null);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    try {
      const r = await api.get('/org-units');
      setTree(r.data.items);
    } catch (e) { message.error(extractError(e)); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const findUnit = (units: Unit[], id: number): Unit | null => {
    for (const u of units) {
      if (u.id === id) return u;
      const f = u.children ? findUnit(u.children, id) : null;
      if (f) return f;
    }
    return null;
  };

  const save = async () => {
    try {
      const v = await form.validateFields();
      if (modal?.unit) {
        await api.put(`/org-units/${modal.unit.id}`, { ...v, parent_id: modal?.parent_id });
      } else {
        await api.post('/org-units', { ...v, parent_id: modal?.parent_id });
      }
      message.success('ذخیره شد');
      setModal(null);
      form.resetFields();
      load();
    } catch (e: any) { if (!e?.errorFields) message.error(extractError(e)); }
  };

  const remove = async (id: number) => {
    try {
      await api.delete(`/org-units/${id}`);
      message.success('حذف شد');
      setSelected(null);
      load();
    } catch (e) { message.error(extractError(e)); }
  };

  return (
    <Row gutter={12}>
      <Col span={14}>
        <Card title="واحدهای سازمانی" size="small"
          extra={
            <Space>
              <Button size="small" icon={<ReloadOutlined />} onClick={load} />
              <Button size="small" type="primary" icon={<PlusOutlined />}
                onClick={() => { setModal({ parent_id: null }); form.resetFields(); }}>واحد ریشه</Button>
            </Space>
          }>
          {tree.length ? (
            <Tree
              treeData={toTree(tree)}
              defaultExpandAll
              onSelect={(keys) => {
                const u = keys.length ? findUnit(tree, Number(keys[0])) : null;
                setSelected(u);
              }}
            />
          ) : <Typography.Text type="secondary">واحدی ثبت نشده است</Typography.Text>}
        </Card>
      </Col>
      <Col span={10}>
        <Card title="جزئیات واحد" size="small"
          extra={selected && (
            <Space size="small">
              <Button size="small" onClick={() => { setModal({ parent_id: selected.id }); form.resetFields(); }}>واحد زیرمجموعه</Button>
              <Button size="small" onClick={() => { setModal({ parent_id: selected.parent_id, unit: selected }); form.setFieldsValue(selected); }}>ویرایش</Button>
              <Popconfirm title="حذف واحد؟" onConfirm={() => remove(selected.id)}>
                <Button size="small" danger>حذف</Button>
              </Popconfirm>
            </Space>
          )}>
          {selected ? (
            <div>
              <Typography.Title level={5}>{selected.name}</Typography.Title>
              <Typography.Text type="secondary" className="mono">{selected.code || '—'}</Typography.Text>
            </div>
          ) : <Typography.Text type="secondary">یک واحد را انتخاب کنید</Typography.Text>}
        </Card>
      </Col>

      <Modal open={!!modal} title={modal?.unit ? 'ویرایش واحد' : 'واحد جدید'} onCancel={() => setModal(null)} onOk={save} okText="ذخیره">
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="نام واحد" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="code" label="کد"><Input className="mono" /></Form.Item>
        </Form>
      </Modal>
    </Row>
  );
}
