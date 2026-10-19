// طراح فرایند BPMN — bpmn-js + تنظیم فعالیت‌ها (فرم/مسئول/نتیجه/کانکتور) + اعتبارسنجی + انتشار
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert, Button, Card, Col, Drawer, Empty, Form, Input, InputNumber, Modal, Row, Select,
  Space, Spin, Tag, Typography, Upload, App as AntApp, Popconfirm, Divider,
} from 'antd';
import {
  DownloadOutlined, FileAddOutlined, SaveOutlined, ThunderboltOutlined,
  UploadOutlined, SettingOutlined,
} from '@ant-design/icons';
import { useParams, useSearchParams } from 'react-router-dom';
import { api, TaskBinding, VersionRow, extractError } from '../api/client';
import FormDesigner from '../components/FormDesigner';
import type { FormSchema } from '../lib/formSchema';

export default function ProcessDesignerPage() {
  const { id } = useParams();
  const [sp, setSp] = useSearchParams();
  const processId = Number(id || 0);
  const versionId = Number(sp.get('v') || 0);
  const { message } = AntApp.useApp();
  const modelerRef = useRef<any>(null);

  const [process, setProcess] = useState<any>(null);
  const [version, setVersion] = useState<VersionRow | null>(null);
  const [xml, setXml] = useState('');
  const [bindings, setBindings] = useState<Record<string, TaskBinding>>({});
  const [selectedEl, setSelectedEl] = useState<{ id: string; name: string; type: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [validation, setValidation] = useState<{ errors: string[]; warnings: string[] } | null>(null);
  const [procs, setProcs] = useState<{ id: string; name: string }[]>([]);
  const [mainPid, setMainPid] = useState('');
  const [calendarId, setCalendarId] = useState<number | null>(null);
  const [newVersionOpen, setNewVersionOpen] = useState(false);
  const [formsList, setFormsList] = useState<{ id: number; title: string }[]>([]);
  const [usersList, setUsersList] = useState<{ id: number; full_name: string }[]>([]);
  const [rolesList, setRolesList] = useState<{ code: string; title: string }[]>([]);
  const [decisionsList, setDecisionsList] = useState<{ id: number; key: string; title: string }[]>([]);
  const [calendarsList, setCalendarsList] = useState<{ id: number; name: string; is_default: boolean }[]>([]);
  const [subformEdit, setSubformEdit] = useState<{ formId: number; title: string } | null>(null);

  const load = useCallback(async () => {
    if (!processId) return;
    try {
      const p = await api.get(`/processes/${processId}`);
      setProcess({ id: p.data.id, key: p.data.key, title: p.data.title, versions: p.data.versions });
      let vid = versionId || p.data.latest_version?.id;
      if (!vid) { message.info('این فرایند هنوز نسخه‌ای ندارد؛ یک BPMN بارگذاری کنید'); return; }
      const v = await api.get(`/processes/versions/${vid}`);
      setVersion(v.data);
      setXml(v.data.bpmn_xml);
      setBindings(v.data.config_json?.bindings || {});
      setCalendarId(v.data.config_json?.calendarId || null);
      setMainPid(v.data.main_process_id);
    } catch (e) { message.error(extractError(e)); }
  }, [processId, versionId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get('/forms').then((r) => setFormsList(r.data.items)).catch(() => {});
    api.get('/users', { params: { page_size: 200 } }).then((r) => setUsersList(r.data.items)).catch(() => {});
    api.get('/roles').then((r) => setRolesList(r.data.items)).catch(() => {});
    api.get('/decisions').then((r) => setDecisionsList(r.data.items)).catch(() => {});
    api.get('/calendars').then((r) => setCalendarsList(r.data.items)).catch(() => {});
  }, []);

  // انتخاب عنصر روی نمودار
  useEffect(() => {
    const m = modelerRef.current;
    if (!m) return;
    const onSel = ({ element }: any) => {
      if (!element || ['bpmn:Process', 'bpmn:Collaboration'].includes(element.type)) { setSelectedEl(null); return; }
      setSelectedEl({ id: element.id, name: element.businessObject?.name || element.id, type: element.type });
    };
    m.on('selection.changed', onSel);
    return () => { m.off('selection.changed', onSel); };
  }, [xml, versionId]);

  const onModelerReady = useCallback((m: any) => {
    modelerRef.current = m;
  }, []);

  const getXml = async (): Promise<string> => {
    const { xml: out } = await modelerRef.current.saveXML({ format: true });
    return out;
  };

  const listProcs = async (content: string) => {
    try {
      const r = await api.post('/processes/parse-ids', { bpmn_xml: content });
      setProcs(r.data.items);
      if (!mainPid && r.data.items.length) {
        const exe = r.data.items.find((x: any) => x.isExecutable) || r.data.items[0];
        setMainPid(exe.id);
      }
    } catch (e) { message.error(extractError(e)); }
  };

  const uploadFile = async (file: File) => {
    const text = await file.text();
    setXml(text);
    await listProcs(text);
    return false;
  };

  const saveVersion = async (publish: boolean, changeNote: string = '', newVersionId?: number) => {
    setSaving(true);
    try {
      const content = await getXml();
      const vid = newVersionId || versionId;
      await api.put(`/processes/versions/${vid}`, {
        bpmn_xml: content,
        main_process_id: mainPid,
        config_json: { bindings, calendarId },
        change_note: changeNote,
      });
      if (publish) {
        const r = await api.post(`/processes/versions/${vid}/publish`);
        if (r.data.warnings?.length) {
          message.warning({ content: `منتشر شد با هشدار: ${r.data.warnings.join(' | ')}`, duration: 8 });
        } else {
          message.success('نسخه فرایند با موفقیت منتشر شد');
        }
      } else {
        message.success('پیش‌نویس ذخیره شد');
      }
      load();
    } catch (e: any) {
      const resp = e?.response?.data?.error;
      if (resp?.errors) {
        message.error({ content: `انتخاب مسدود شد — خطاها: ${resp.errors.join(' | ')}`, duration: 10 });
        setValidation({ errors: resp.errors, warnings: resp.warnings || [] });
      } else {
        message.error(extractError(e));
      }
    } finally { setSaving(false); }
  };

  const validateNow = async () => {
    try {
      const content = await getXml();
      // ابتدا ذخیره موقت محتوای جاری برای اعتبارسنجی دقیق
      await api.put(`/processes/versions/${versionId}`, {
        bpmn_xml: content, main_process_id: mainPid, config_json: { bindings, calendarId }, change_note: version?.change_note || '',
      });
      const r = await api.post(`/processes/versions/${versionId}/validate`);
      setValidation(r.data);
      if (!r.data.errors.length && !r.data.warnings.length) message.success('مدل از نظر ساختاری و اتصالات معتبر است');
    } catch (e) { message.error(extractError(e)); }
  };

  const downloadXml = async () => {
    const content = await getXml();
    const blob = new Blob([content], { type: 'text/xml' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${process?.key || 'process'}.bpmn`;
    a.click();
  };

  const downloadSvg = async () => {
    try {
      const { svg } = await modelerRef.current.saveSVG();
      const blob = new Blob([svg], { type: 'image/svg+xml' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `${process?.key || 'process'}.svg`;
      a.click();
    } catch (e) { message.error('خروجی SVG ممکن نشد'); }
  };

  const patchBinding = (specId: string, key: keyof TaskBinding, value: unknown) => {
    setBindings((b) => ({ ...b, [specId]: { ...(b[specId] || {}), [key]: value } }));
  };

  const binding = selectedEl ? bindings[selectedEl.id] || {} : null;
  const isUserTask = selectedEl?.type === 'bpmn:UserTask';
  const isServiceTask = selectedEl?.type === 'bpmn:ServiceTask';
  const isStart = selectedEl?.type === 'bpmn:StartEvent';
  const configurable = isUserTask || isServiceTask || isStart;

  // حالت طراحی زیرفرم فرم متصل
  if (subformEdit) {
    return (
      <div>
        <Button type="link" onClick={() => { setSubformEdit(null); load(); }}>بازگشت به طراح فرایند</Button>
        <SubformDesignerLoader formId={subformEdit.formId} title={subformEdit.title} />
      </div>
    );
  }

  return (
    <Card
      title={`طراح فرایند: ${process?.title || ''} ${version ? `— نسخه v${version.version} (${version.status === 'draft' ? 'پیش‌نویس' : version.status === 'published' ? 'منتشرشده' : version.status})` : ''}`}
      extra={
        <Space wrap>
          <Upload beforeUpload={(f) => uploadFile(f as unknown as File)} showUploadList={false} accept=".bpmn,.xml">
            <Button icon={<UploadOutlined />}>باز کردن فایل BPMN</Button>
          </Upload>
          <Button icon={<DownloadOutlined />} onClick={downloadXml}>BPMN</Button>
          <Button icon={<DownloadOutlined />} onClick={downloadSvg}>SVG</Button>
          {version?.status === 'draft' && (
            <>
              <Button icon={<SaveOutlined />} loading={saving} onClick={() => saveVersion(false)}>ذخیره پیش‌نویس</Button>
              <Popconfirm title="اعتبارسنجی و انتشار؟ خطاهای قطعی مانع انتشار می‌شوند." onConfirm={() => saveVersion(true)}>
                <Button type="primary" icon={<ThunderboltOutlined />} loading={saving}>انتشار نسخه</Button>
              </Popconfirm>
            </>
          )}
          {version?.status !== 'draft' && (
            <Button icon={<FileAddOutlined />} onClick={() => setNewVersionOpen(true)}>نسخه جدید از این مدل</Button>
          )}
          <Button onClick={validateNow}>اعتبارسنجی</Button>
        </Space>
      }
    >
      {!version && <Empty description="نسخه‌ای برای طراحی وجود ندارد — یک فرایند جدید ایجاد کنید یا فایل BPMN بارگذاری نمایید" />}
      {procs.length > 0 && (
        <Alert style={{ marginBottom: 10 }} type="info"
          message={<Space>فرایند اصلی: <Select size="small" style={{ minWidth: 260 }} value={mainPid} onChange={setMainPid}
            options={procs.map((p: any) => ({ value: p.id, label: `${p.name} (${p.id})` }))} /></Space>} />
      )}
      {version && (
        <Alert style={{ marginBottom: 10 }} type="info"
          message={<Space wrap>
            <span>تقویم کاری نسخه (برای محاسبه مهلت وظایف):</span>
            <Select size="small" style={{ minWidth: 240 }} allowClear placeholder="بدون تقویم (مهلت خطی)"
              value={calendarId}
              onChange={(v) => setCalendarId(v ?? null)}
              options={calendarsList.map((c) => ({ value: c.id, label: `${c.name}${c.is_default ? ' — پیش‌فرض' : ''}` }))} />
          </Space>} />
      )}
      {validation && (
        <Alert style={{ marginBottom: 10 }} type={validation.errors.length ? 'error' : 'warning'} closable
          message={validation.errors.length ? 'خطاهای قطعی (مانع انتشار)' : 'هشدارها (انتشار ممکن است)'}
          description={
            <ul style={{ margin: 0, paddingRight: 18 }}>
              {validation.errors.map((e, i) => <li key={i}><Tag color="red">خطا</Tag>{e}</li>)}
              {validation.warnings.map((e, i) => <li key={`w${i}`}><Tag color="orange">هشدار</Tag>{e}</li>)}
            </ul>
          } />
      )}
      {xml && (
        <Row gutter={12}>
          <Col span={18}>
            <ModelerHost xml={xml} onReady={onModelerReady} onParsed={(p) => { setProcs(p); if (!mainPid && p.length) setMainPid((p.find((x: any) => x.isExecutable) || p[0]).id); }} />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              برای تنظیم فرم/مسئول/نتیجه، فعالیت موردنظر را روی نمودار انتخاب کنید تا پنل تنظیمات باز شود.
            </Typography.Text>
          </Col>
          <Col span={6}>
            <Card size="small" title={<span><SettingOutlined /> تنظیمات فعالیت انتخابی</span>} styles={{ body: { minHeight: 300 } }}>
              {!selectedEl && <Alert type="info" message="ابتدا یک عنصر را روی نمودار انتخاب کنید" />}
              {selectedEl && !configurable && (
                <Alert type="info" message={`عنصر «${selectedEl.name}» (${selectedEl.type}) تنظیم خاصی ندارد`} />
              )}
              {selectedEl && configurable && (
                <Form layout="vertical" size="small">
                  <Divider style={{ margin: '4px 0 12px' }} />
                  <Typography.Text strong>{selectedEl.name}</Typography.Text>
                  <Typography.Paragraph type="secondary" style={{ fontSize: 11 }} className="mono">{selectedEl.id}</Typography.Paragraph>

                  {(isStart || isUserTask) && (
                    <Form.Item label="فرم متصل (منتشرشده)">
                      <Select allowClear placeholder="انتخاب فرم" value={binding?.formDefinitionId || null}
                        onChange={(v) => patchBinding(selectedEl.id, 'formDefinitionId', v)}
                        options={formsList.map((f) => ({ value: f.id, label: f.title }))} />
                    </Form.Item>
                  )}
                  {isUserTask && (
                    <Form.Item label="جدول تصمیم متصل (DMN) — خروجی به متغیرهای فرایند ادغام می‌شود">
                      <Select allowClear showSearch optionFilterProp="label" placeholder="بدون جدول تصمیم"
                        value={binding?.decisionKey || null}
                        onChange={(v) => patchBinding(selectedEl.id, 'decisionKey', v)}
                        options={decisionsList.map((d) => ({ value: d.key, label: `${d.title} (${d.key})` }))} />
                    </Form.Item>
                  )}
                  {isUserTask && (
                    <>
                      <Form.Item label="نوع مسئول">
                        <Select value={binding?.assigneeType || undefined} allowClear placeholder="انتخاب"
                          onChange={(v) => patchBinding(selectedEl.id, 'assigneeType', v)}
                          options={[
                            { value: 'role', label: 'نقش / گروه کاری' },
                            { value: 'user', label: 'کاربر مشخص' },
                            { value: 'field', label: 'بر اساس داده فرایند (فیلد)' },
                            { value: 'self', label: 'شروع‌کننده درخواست' },
                          ]} />
                      </Form.Item>
                      {binding?.assigneeType === 'role' && (
                        <Form.Item label="نقش نامزد">
                          <Select value={binding?.assigneeValue as string || undefined} allowClear placeholder="انتخاب نقش"
                            onChange={(v) => patchBinding(selectedEl.id, 'assigneeValue', v)}
                            options={rolesList.map((r) => ({ value: r.code, label: r.title }))} />
                        </Form.Item>
                      )}
                      {binding?.assigneeType === 'user' && (
                        <Form.Item label="کاربر">
                          <Select value={binding?.assigneeValue as number || undefined} allowClear showSearch optionFilterProp="label"
                            onChange={(v) => patchBinding(selectedEl.id, 'assigneeValue', v)}
                            options={usersList.map((u) => ({ value: u.id, label: u.full_name }))} />
                        </Form.Item>
                      )}
                      {binding?.assigneeType === 'field' && (
                        <Form.Item label="نام فیلد داده (مثال: _initiator_id)">
                          <Input className="mono" value={binding?.assigneeValue as string || ''} onChange={(e) => patchBinding(selectedEl.id, 'assigneeValue', e.target.value)} />
                        </Form.Item>
                      )}
                      <Form.Item label="مهلت انجام (ساعت)">
                        <InputNumber min={1} style={{ width: '100%' }} value={binding?.dueHours || undefined}
                          onChange={(v) => patchBinding(selectedEl.id, 'dueHours', v)} />
                      </Form.Item>
                      <Form.Item label="نتیجه‌های مجاز اقدام کاربر (دکمه‌ها)">
                        <Select mode="tags" placeholder="مثال: approve=تأیید"
                          value={(binding?.results || []).map((r) => `${r.value}=${r.label}`)}
                          onChange={(arr) => patchBinding(selectedEl.id, 'results', arr.map((s: string) => {
                            const [value, ...rest] = s.split('=');
                            return { value: value.trim(), label: (rest.join('=') || value).trim() };
                          }))} />
                      </Form.Item>
                    </>
                  )}
                  {isServiceTask && (
                    <Form.Item label="کانکتور (نمونه: mock:register_order یا http:POST:https://...)">
                      <Input className="mono" value={binding?.connector || ''} placeholder="mock:register_order"
                        onChange={(e) => patchBinding(selectedEl.id, 'connector', e.target.value)} />
                    </Form.Item>
                  )}
                  {(isStart || isUserTask) && binding?.formDefinitionId && (
                    <Button block size="small" onClick={() => setSubformEdit({
                      formId: binding.formDefinitionId as number,
                      title: formsList.find((f) => f.id === binding.formDefinitionId)?.title || 'فرم',
                    })}>ویرایش فرم در فرم‌ساز</Button>
                  )}
                </Form>
              )}
            </Card>
          </Col>
        </Row>
      )}

      <Modal open={newVersionOpen} title="ایجاد نسخه جدید" onCancel={() => setNewVersionOpen(false)}
        onOk={async () => {
          try {
            const content = await getXml();
            const r = await api.post(`/processes/${processId}/versions`, {
              bpmn_xml: content, main_process_id: mainPid, config_json: { bindings, calendarId },
              change_note: 'نسخه جدید از مدل جاری',
            });
            message.success('نسخه پیش‌نویس جدید ساخته شد');
            setNewVersionOpen(false);
            setSp({ v: String(r.data.id) });
            load();
          } catch (e) { message.error(extractError(e)); }
        }} okText="ایجاد">
        نسخه پیش‌نویس جدیدی از مدل جاری ساخته می‌شود؛ نمونه‌های جاری به نسخه قبلی خود متصل می‌مانند (AC-14).
      </Modal>
    </Card>
  );
}

// میزبان Modeler با لود XML — جدا برای مدیریت lifecycle
function ModelerHost({ xml, onReady, onParsed }: { xml: string; onReady: (m: any) => void; onParsed: (p: any[]) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const mRef = useRef<any>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!ref.current) return;
    import('bpmn-js/lib/Modeler').then((Mod) => {
      const m = new Mod.default({ container: ref.current as HTMLElement, keyboard: { bindTo: document } });
      mRef.current = m;
      onReady(m);
      setReady(true);
    });
    return () => { mRef.current?.destroy(); mRef.current = null; };
  }, []);

  useEffect(() => {
    const m = mRef.current;
    if (!m || !xml || !ready) return;
    m.importXML(xml).then(() => {
      m.get('canvas').zoom('fit-viewport');
      // فهرست فرایندهای فایل
      try {
        const defs = m.getDefinitions();
        const items = (defs.rootElements || [])
          .filter((e: any) => e.$type === 'bpmn:Process')
          .map((e: any) => ({ id: e.id, name: e.name || e.id, isExecutable: e.isExecutable }));
        onParsed(items);
      } catch { /* ignore */ }
    }).catch((e: Error) => console.error('import failed', e));
  }, [xml, ready]);

  return <div ref={ref} className="bpmn-canvas" style={{ height: 'calc(100vh - 320px)' }} />;
}

// بارگذار زیرفرم در فرم‌ساز
function SubformDesignerLoader({ formId, title }: { formId: number; title: string }) {
  const [latest, setLatest] = useState<any>(null);
  useEffect(() => {
    api.get(`/forms/${formId}`).then(async (r) => {
      const vid = r.data.latest_version?.id;
      if (vid) {
        const v = await api.get(`/forms/versions/${vid}`);
        setLatest({ form: r.data, version: v.data });
      }
    }).catch(() => {});
  }, [formId]);
  if (!latest) return <Spin />;
  return (
    <FormDesigner
      formId={formId} formTitle={title}
      versionId={latest.version.id} versionStatus={latest.version.status}
      initialSchema={latest.version.schema_json as FormSchema}
      changeNote={latest.version.change_note}
      onSaved={() => window.location.reload()}
    />
  );
}
