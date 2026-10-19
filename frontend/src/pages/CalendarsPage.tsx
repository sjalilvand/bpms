// تقویم کاری (فاز ۳) — برنامه هفتگی، تعطیلات جلالی، پیش‌نمایش مهلت کاری
import { useCallback, useEffect, useState } from 'react';
import {
  Alert, App as AntApp, Button, Card, Checkbox, Empty, Form, Input, InputNumber,
  Modal, Popconfirm, Select, Space, Spin, Table, Tag, TimePicker, Typography,
} from 'antd';
import { CalendarOutlined, DeleteOutlined, PlusOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import {
  api, CalendarRow, DayRuleT, extractError, Paged,
} from '../api/client';
import { useAuth } from '../auth/AuthContext';
import JalaliDatePicker from '../components/JalaliDatePicker';

const DAY_ORDER: { key: string; label: string }[] = [
  { key: 'saturday', label: 'شنبه' }, { key: 'sunday', label: 'یکشنبه' },
  { key: 'monday', label: 'دوشنبه' }, { key: 'tuesday', label: 'سه‌شنبه' },
  { key: 'wednesday', label: 'چهارشنبه' }, { key: 'thursday', label: 'پنجشنبه' },
  { key: 'friday', label: 'جمعه' },
];

const emptyDay = (): DayRuleT => ({ enabled: false, start: '08:00', end: '16:00', breaks: [] });

function defaultSchedule(): Record<string, DayRuleT> {
  const out: Record<string, DayRuleT> = {};
  DAY_ORDER.forEach(({ key }) => { out[key] = emptyDay(); });
  return out;
}

const hmToDayjs = (v?: string) => dayjs(`${dayjs().format('YYYY-MM-DD')} ${v || '08:00'}`, 'YYYY-MM-DD HH:mm');
const dayjsToHm = (d: Dayjs | null) => (d ? d.format('HH:mm') : '08:00');

export default function CalendarsPage() {
  const { message } = AntApp.useApp();
  const { user, hasPerm } = useAuth();
  const canManage = user?.is_superadmin || hasPerm('calendar.manage');

  const [rows, setRows] = useState<CalendarRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<CalendarRow | null>(null);
  const [schedule, setSchedule] = useState<Record<string, DayRuleT>>(defaultSchedule());
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [saving, setSaving] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();

  const [holidayOpen, setHolidayOpen] = useState(false);
  const [holidayDate, setHolidayDate] = useState<string | null>(null);
  const [holidayTitle, setHolidayTitle] = useState('');
  const [holidayYearly, setHolidayYearly] = useState(false);

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewHours, setPreviewHours] = useState<number>(8);
  const [previewResult, setPreviewResult] = useState<string>('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get<Paged<CalendarRow>>('/calendars');
      setRows(r.data.items);
    } catch (e) { message.error(extractError(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openEditor = async (id: number) => {
    try {
      const r = await api.get<CalendarRow>(`/calendars/${id}`);
      setEditing(r.data);
      setName(r.data.name);
      setDesc(r.data.description || '');
      setSchedule({ ...defaultSchedule(), ...(r.data.schedule_json || {}) });
    } catch (e) { message.error(extractError(e)); }
  };

  const save = async () => {
    if (!editing) return;
    setSaving(true);
    try {
      await api.put(`/calendars/${editing.id}`, {
        name, description: desc, timezone: editing.timezone,
        schedule_json: schedule, is_default: editing.is_default,
      });
      message.success('تقویم ذخیره شد');
      await load();
      await openEditor(editing.id);
    } catch (e) { message.error(extractError(e)); }
    finally { setSaving(false); }
  };

  const create = async () => {
    try {
      const v = await createForm.validateFields();
      const r = await api.post('/calendars', { ...v, schedule_json: defaultSchedule() });
      message.success('تقویم ایجاد شد');
      setCreateOpen(false);
      createForm.resetFields();
      await load();
      openEditor(r.data.id);
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(extractError(e));
    }
  };

  const setDefault = async (c: CalendarRow) => {
    try {
      await api.put(`/calendars/${c.id}`, {
        name: c.name, description: c.description, timezone: c.timezone,
        schedule_json: c.schedule_json, is_default: true,
      });
      message.success(`«${c.name}» تقویم پیش‌فرض شد`);
      await load();
    } catch (e) { message.error(extractError(e)); }
  };

  const addHoliday = async () => {
    if (!editing || !holidayDate) return;
    try {
      await api.post(`/calendars/${editing.id}/holidays`, {
        date: holidayDate, title: holidayTitle, yearly: holidayYearly,
      });
      message.success('تعطیلی ثبت شد');
      setHolidayOpen(false);
      setHolidayTitle('');
      setHolidayDate(null);
      setHolidayYearly(false);
      await openEditor(editing.id);
    } catch (e) { message.error(extractError(e)); }
  };

  const removeHoliday = async (hid: number) => {
    if (!editing) return;
    try {
      await api.delete(`/calendars/${editing.id}/holidays/${hid}`);
      await openEditor(editing.id);
    } catch (e) { message.error(extractError(e)); }
  };

  const runPreview = async () => {
    if (!editing) return;
    try {
      const r = await api.post(`/calendars/${editing.id}/preview`, { hours: previewHours });
      setPreviewResult(`مهلت کاری ${previewHours} ساعت از اکنون: ${r.data.due_at_jalali}`);
    } catch (e) { setPreviewResult('خطا: ' + extractError(e)); }
  };

  const patchDay = (key: string, patch: Partial<DayRuleT>) => {
    setSchedule((s) => ({ ...s, [key]: { ...emptyDay(), ...(s[key] || {}), ...patch } }));
  };

  if (editing) {
    return (
      <div>
        <Card
          title={<Space><CalendarOutlined /> تقویم کاری: {name}{editing.is_default && <Tag color="green">پیش‌فرض</Tag>}</Space>}
          extra={
            <Space wrap>
              {canManage && <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={save}>ذخیره</Button>}
              <Button icon={<PlusOutlined />} onClick={() => setHolidayOpen(true)}>تعطیلی جدید</Button>
              <Button onClick={() => { setPreviewOpen(true); setPreviewResult(''); }}>پیش‌نمایش مهلت</Button>
              <Button onClick={() => setEditing(null)}>بازگشت</Button>
            </Space>
          }
        >
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            <Space wrap>
              <Input style={{ width: 280 }} value={name} onChange={(e) => setName(e.target.value)} placeholder="نام تقویم" />
              <Input style={{ width: 380 }} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="توضیح" />
            </Space>
            <Alert type="info" showIcon message="ساعت‌ها به وقت محلی (Asia/Tehran) است. مهلت وظایف بر پایه همین ساعات کاری محاسبه می‌شود." />
            <Table
              size="small" pagination={false} rowKey="key"
              dataSource={DAY_ORDER}
              columns={[
                { title: 'روز', dataIndex: 'label', key: 'label', width: 110, render: (l: string) => <Typography.Text strong>{l}</Typography.Text> },
                {
                  title: 'روز کاری', key: 'enabled', width: 100,
                  render: (_: unknown, d: { key: string }) => (
                    <Checkbox checked={!!schedule[d.key]?.enabled}
                      disabled={!canManage}
                      onChange={(e) => patchDay(d.key, { enabled: e.target.checked })} />
                  ),
                },
                {
                  title: 'از ساعت', key: 'start', width: 130,
                  render: (_: unknown, d: { key: string }) => (
                    <TimePicker format="HH:mm" minuteStep={15} disabled={!canManage || !schedule[d.key]?.enabled}
                      value={hmToDayjs(schedule[d.key]?.start)}
                      onChange={(v) => patchDay(d.key, { start: dayjsToHm(v) })} />
                  ),
                },
                {
                  title: 'تا ساعت', key: 'end', width: 130,
                  render: (_: unknown, d: { key: string }) => (
                    <TimePicker format="HH:mm" minuteStep={15} disabled={!canManage || !schedule[d.key]?.enabled}
                      value={hmToDayjs(schedule[d.key]?.end)}
                      onChange={(v) => patchDay(d.key, { end: dayjsToHm(v) })} />
                  ),
                },
                {
                  title: 'وقفه‌ها', key: 'breaks',
                  render: (_: unknown, d: { key: string }) => {
                    const day = schedule[d.key] || emptyDay();
                    return (
                      <Space direction="vertical" size={4}>
                        {(day.breaks || []).map((b, i) => (
                          <Space key={i} size={4}>
                            <TimePicker size="small" format="HH:mm" minuteStep={15} disabled={!canManage}
                              value={hmToDayjs(b.start)} onChange={(v) => {
                                const breaks = day.breaks.map((x, xi) => (xi === i ? { ...x, start: dayjsToHm(v) } : x));
                                patchDay(d.key, { breaks });
                              }} />
                            <span>تا</span>
                            <TimePicker size="small" format="HH:mm" minuteStep={15} disabled={!canManage}
                              value={hmToDayjs(b.end)} onChange={(v) => {
                                const breaks = day.breaks.map((x, xi) => (xi === i ? { ...x, end: dayjsToHm(v) } : x));
                                patchDay(d.key, { breaks });
                              }} />
                            {canManage && (
                              <Button size="small" type="text" danger icon={<DeleteOutlined />}
                                onClick={() => patchDay(d.key, { breaks: day.breaks.filter((_, xi) => xi !== i) })} />
                            )}
                          </Space>
                        ))}
                        {canManage && (
                          <Button size="small" type="dashed" icon={<PlusOutlined />}
                            onClick={() => patchDay(d.key, { breaks: [...(day.breaks || []), { start: '12:00', end: '13:00' }] })}>
                            وقفه
                          </Button>
                        )}
                      </Space>
                    );
                  },
                },
              ]}
            />

            <Card size="small" title="تعطیلات رسمی">
              {(editing.holidays?.length || 0) === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="تعطیلی ثبت نشده است" />}
              {(editing.holidays || []).map((h) => (
                <Space key={h.id} style={{ marginBottom: 6 }} wrap>
                  <Tag color="red">{h.date_jalali || h.date}</Tag>
                  <Tag color={h.yearly ? 'purple' : 'default'}>{h.yearly ? 'سالانه' : 'یک‌باره'} — {h.date}</Tag>
                  <Typography.Text>{h.title}</Typography.Text>
                  {canManage && (
                    <Popconfirm title="حذف تعطیلی؟" onConfirm={() => removeHoliday(h.id)}>
                      <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  )}
                </Space>
              ))}
            </Card>
          </Space>
        </Card>

        <Modal open={holidayOpen} title="تعطیلی جدید" onOk={addHoliday} onCancel={() => setHolidayOpen(false)} okText="ثبت">
          <Space direction="vertical" style={{ width: '100%' }}>
            <JalaliDatePicker value={holidayDate} onChange={setHolidayDate} placeholder="انتخاب تاریخ (جلالی)" />
            <Input value={holidayTitle} onChange={(e) => setHolidayTitle(e.target.value)} placeholder="عنوان (مثال: نوروز)" />
            <Checkbox checked={holidayYearly} onChange={(e) => setHolidayYearly(e.target.checked)}>
              تکرار سالانه (تعطیلات ثابت تقویم)
            </Checkbox>
          </Space>
        </Modal>

        <Modal open={previewOpen} title="پیش‌نمایش مهلت کاری" onCancel={() => setPreviewOpen(false)}
          footer={<Button onClick={() => setPreviewOpen(false)}>بستن</Button>}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Space>
              <span>ساعت کاری:</span>
              <InputNumber min={0.5} step={0.5} value={previewHours} onChange={(v) => setPreviewHours(v || 1)} />
              <Button type="primary" onClick={runPreview}>محاسبه</Button>
            </Space>
            {previewResult && <Alert type="info" message={previewResult} />}
          </Space>
        </Modal>
      </div>
    );
  }

  return (
    <div>
      <Card
        title={<Space><CalendarOutlined /> تقویم‌های کاری</Space>}
        extra={canManage && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>تقویم جدید</Button>
        )}
      >
        <Table<CalendarRow>
          rowKey="id" loading={loading} dataSource={rows} pagination={false}
          locale={{ emptyText: <Empty description="تقویمی تعریف نشده است" /> }}
          columns={[
            { title: 'نام', dataIndex: 'name', key: 'name' },
            { title: 'منطقه زمانی', dataIndex: 'timezone', key: 'tz', width: 140 },
            {
              title: 'پیش‌فرض', key: 'def', width: 110,
              render: (_: unknown, c: CalendarRow) => c.is_default ? <Tag color="green">پیش‌فرض</Tag> : (
                canManage && <Button size="small" onClick={() => setDefault(c)}>تنظیم به‌عنوان پیش‌فرض</Button>
              ),
            },
            { title: 'تعطیلات', dataIndex: 'holiday_count', key: 'hol', width: 90 },
            {
              title: 'عملیات', key: 'act', width: 200,
              render: (_: unknown, c: CalendarRow) => (
                <Space>
                  <Button size="small" onClick={() => openEditor(c.id)}>ویرایش</Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal open={createOpen} title="تقویم کاری جدید" onOk={create} onCancel={() => setCreateOpen(false)} okText="ایجاد">
        <Form form={createForm} layout="vertical" initialValues={{ timezone: 'Asia/Tehran' }}>
          <Form.Item name="name" label="نام" rules={[{ required: true, message: 'نام الزامی است' }]}>
            <Input placeholder="تقویم کاری ستاد مرکزی" />
          </Form.Item>
          <Form.Item name="description" label="توضیح"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="timezone" label="منطقه زمانی">
            <Select options={[{ value: 'Asia/Tehran', label: 'Asia/Tehran (تهران)' }, { value: 'UTC', label: 'UTC' }]} />
          </Form.Item>
        </Form>
      </Modal>
      {loading && <Spin style={{ display: 'block', margin: '20px auto' }} />}
    </div>
  );
}
