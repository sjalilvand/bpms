// داده‌های پایه — جداول پایه و آیتم‌های سلسله‌مراتبی
import { useCallback, useEffect, useState } from 'react';
import {
  Button, Card, Col, Form, Input, InputNumber, Modal, Popconfirm, Row, Space, Switch,
  Table, Tag, Tree, Typography, App as AntApp,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import type { DataNode } from 'antd/es/tree';
import { api, Paged, extractError } from '../api/client';

interface LookupDef { id: number; key: string; title: string; description: string }
interface LookupItemT {
  id: number; code: string; title: string; parent_id: number | null;
  sort_order: number; is_active: boolean; children?: LookupItemT[];
}

function toTreeData(items: LookupItemT[]): DataNode[] {
  return items.map((it) => ({
    key: it.id,
    title: `${it.title} ${it.is_active ? '' : '(غیرفعال)'}`,
    children: it.children?.length ? toTreeData(it.children) : undefined,
  }));
}

export default function LookupsPage() {
  const { message } = AntApp.useApp();
  const [defs, setDefs] = useState<LookupDef[]>([]);
  const [selected, setSelected] = useState<LookupDef | null>(null);
  const [items, setItems] = useState<LookupItemT[]>([]);
  const [loading, setLoading] = useState(false);
  const [defModal, setDefModal] = useState(false);
  const [itemModal, setItemModal] = useState<null | { parent_id: number | null; item?: LookupItemT }>(null);
  const [form] = Form.useForm();
  const [itemForm] = Form.useForm();

  const loadDefs = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get<Paged<LookupDef>>('/lookups');
      setDefs(r.data.items);
      if (r.data.items.length && !selected) selectDef(r.data.items[0]);
    } catch (e) { message.error(extractError(e)); }
    finally { setLoading(false); }
  }, []);

  const selectDef = async (d: LookupDef) => {
    setSelected(d);
    try {
      const r = await api.get(`/lookups/${d.id}/items`);
      setItems(r.data.items);
    } catch { setItems([]); }
  };

  useEffect(() => { loadDefs(); }, [loadDefs]);

  const createDef = async () => {
    try {
      const v = await form.validateFields();
      await api.post('/lookups', v);
      message.success('جدول پایه ایجاد شد');
      setDefModal(false);
      form.resetFields();
      loadDefs();
    } catch (e: any) { if (!e?.errorFields) message.error(extractError(e)); }
  };

  const saveItem = async () => {
    try {
      const v = await itemForm.validateFields();
      if (itemModal?.item) {
        await api.put(`/lookups/items/${itemModal.item.id}`, { ...v, parent_id: itemModal?.parent_id });
      } else {
        await api.post(`/lookups/${selected?.id}/items`, { ...v, parent_id: itemModal?.parent_id });
      }
      message.success('ذخیره شد');
      setItemModal(null);
      itemForm.resetFields();
      if (selected) selectDef(selected);
    } catch (e: any) { if (!e?.errorFields) message.error(extractError(e)); }
  };

  const deleteItem = async (id: number) => {
    try {
      await api.delete(`/lookups/items/${id}`);
      message.success('حذف شد');
      if (selected) selectDef(selected);
    } catch (e) { message.error(extractError(e)); }
  };

  const flatten = (rows: LookupItemT[], depth = 0): (LookupItemT & { depth: number })[] =>
    rows.flatMap((r) => [{ ...r, depth }, ...flatten(r.children || [], depth + 1)]);

  return (
    <Row gutter={12}>
      <Col span={8}>
        <Card title="جداول پایه" size="small"
          extra={<Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => setDefModal(true)}>جدید</Button>}>
          <Table
            rowKey="id" size="small" loading={loading} dataSource={defs} pagination={false}
            onRow={(r) => ({ onClick: () => selectDef(r), style: { cursor: 'pointer', background: selected?.id === r.id ? '#e0f2f1' : undefined } })}
            columns={[{ title: 'عنوان', dataIndex: 'title' }, { title: 'کلید', dataIndex: 'key', render: (v: string) => <span className="mono">{v}</span> }]}
          />
        </Card>
      </Col>
      <Col span={16}>
        <Card
          size="small" title={selected ? `آیتم‌های «${selected.title}»` : 'آیتم‌ها'}
          extra={
            <Space>
              <Button size="small" icon={<ReloadOutlined />} onClick={() => selected && selectDef(selected)} />
              <Button size="small" type="primary" disabled={!selected}
                onClick={() => { setItemModal({ parent_id: null }); itemForm.resetFields(); }}>آیتم ریشه</Button>
            </Space>
          }
        >
          {!selected && <Typography.Text type="secondary">یک جدول پایه انتخاب کنید</Typography.Text>}
          {selected && (
            <Table
              rowKey="id" size="small" pagination={false}
              dataSource={flatten(items) as any}
              columns={[
                {
                  title: 'عنوان', dataIndex: 'title',
                  render: (_: unknown, r: any) => (
                    <span style={{ paddingRight: r.depth * 20 }}>
                      {r.depth > 0 && '↳ '}{r.title} {!r.is_active && <Tag color="default">غیرفعال</Tag>}
                    </span>
                  ),
                },
                { title: 'کد', dataIndex: 'code', render: (v: string) => <span className="mono">{v}</span> },
                { title: 'ترتیب', dataIndex: 'sort_order', width: 70 },
                {
                  title: 'عملیات', key: 'act', width: 220,
                  render: (_: unknown, r: LookupItemT) => (
                    <Space size="small">
                      <Button size="small" type="link" onClick={() => { setItemModal({ parent_id: r.id }); itemForm.resetFields(); }}>زیرآیتم</Button>
                      <Button size="small" type="link" onClick={() => {
                        setItemModal({ parent_id: r.parent_id, item: r });
                        itemForm.setFieldsValue(r);
                      }}>ویرایش</Button>
                      <Popconfirm title="حذف آیتم؟" onConfirm={() => deleteItem(r.id)}>
                        <Button size="small" type="link" danger>حذف</Button>
                      </Popconfirm>
                    </Space>
                  ),
                },
              ]}
            />
          )}
        </Card>
      </Col>

      <Modal open={defModal} title="جدول پایه جدید" onCancel={() => setDefModal(false)} onOk={createDef} okText="ایجاد">
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="عنوان" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="key" label="کلید (لاتین)" rules={[{ required: true, pattern: /^[a-z][a-z0-9_]*$/i }]}><Input className="mono" /></Form.Item>
          <Form.Item name="description" label="توضیح"><Input /></Form.Item>
        </Form>
      </Modal>

      <Modal open={!!itemModal} title={itemModal?.item ? 'ویرایش آیتم' : 'آیتم جدید'} onCancel={() => setItemModal(null)} onOk={saveItem} okText="ذخیره">
        <Form form={itemForm} layout="vertical">
          <Form.Item name="title" label="عنوان" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="code" label="کد" rules={[{ required: true }]}><Input className="mono" /></Form.Item>
          <Form.Item name="sort_order" label="ترتیب نمایش" initialValue={0}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="is_active" label="فعال" valuePropName="checked" initialValue={true}><Switch /></Form.Item>
        </Form>
      </Modal>
    </Row>
  );
}
