// طراح فرایند BPMN — bpmn-js + تنظیم فعالیت‌ها (فرم/مسئول/نتیجه/کانکتور) + شرط‌ساز بصری جریان‌ها + اعتبارسنجی + انتشار
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert, Button, Card, Col, ColorPicker, Divider, Drawer, Empty, Form, Input, InputNumber, Modal, Row, Select,
  Space, Spin, Tag, Typography, Upload, App as AntApp, Popconfirm,
} from 'antd';
import {
  DownloadOutlined, FileAddOutlined, SaveOutlined, ThunderboltOutlined,
  UploadOutlined, SettingOutlined, FilterOutlined, DeleteOutlined, PlayCircleOutlined, BgColorsOutlined, BankOutlined,
} from '@ant-design/icons';
import { useParams, useSearchParams } from 'react-router-dom';
import { api, TaskBinding, VersionRow, extractError } from '../api/client';
import FormDesigner from '../components/FormDesigner';
import ConditionBuilder from '../components/ConditionBuilder';
import type { FormSchema } from '../lib/formSchema';
import { CondGroup, emptyCondition, isGatewayFlow, parseCondition, renderCondition } from '../lib/conditions';
import { BpmsCompletePaletteModule } from '../lib/bpmnCompletePalette';

// جفت‌رنگ‌های سازمانی برای رنگ‌آمیزی عناصر نمودار (خط + پس‌زمینه ملایم)
const PROCESS_COLORS: { name: string; stroke: string; fill: string }[] = [
  { name: 'آبی', stroke: '#1d4ed8', fill: '#dbeafe' },
  { name: 'فیروزه‌ای', stroke: '#0e7490', fill: '#cffafe' },
  { name: 'سبز', stroke: '#059669', fill: '#d1fae5' },
  { name: 'کهربایی', stroke: '#d97706', fill: '#fef3c7' },
  { name: 'قرمز', stroke: '#dc2626', fill: '#fee2e2' },
  { name: 'بنفش', stroke: '#7c3aed', fill: '#ede9fe' },
  { name: 'خاکستری', stroke: '#475569', fill: '#e2e8f0' },
  { name: 'صورتی', stroke: '#db2777', fill: '#fce7f3' },
];

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
  const [selectedEl, setSelectedEl] = useState<{ id: string; name: string; type: string; sourceType?: string } | null>(null);
  const selElRef = useRef<any>(null);
  // شرط‌ساز بصری (فاز ۴)
  const [condGroup, setCondGroup] = useState<CondGroup | null>(null);
  const [condMode, setCondMode] = useState<'none' | 'visual' | 'manual'>('none');
  const [condManual, setCondManual] = useState('');
  const [hasCondition, setHasCondition] = useState(false);
  const [condVarOptions, setCondVarOptions] = useState<string[]>(['action', 'business_key']);
  const [condSample, setCondSample] = useState('{"action": "approve"}');
  const [condEval, setCondEval] = useState<{ ok: boolean; result?: boolean; msg: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [validation, setValidation] = useState<{ errors: string[]; warnings: string[] } | null>(null);
  const [procs, setProcs] = useState<{ id: string; name: string }[]>([]);
  const [mainPid, setMainPid] = useState('');
  const [calendarId, setCalendarId] = useState<number | null>(null);
  const [newVersionOpen, setNewVersionOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [formsList, setFormsList] = useState<{ id: number; title: string }[]>([]);
  const [usersList, setUsersList] = useState<{ id: number; full_name: string }[]>([]);
  const [rolesList, setRolesList] = useState<{ code: string; title: string }[]>([]);
  const [decisionsList, setDecisionsList] = useState<{ id: number; key: string; title: string }[]>([]);
  const [calendarsList, setCalendarsList] = useState<{ id: number; name: string; is_default: boolean }[]>([]);
  const [subformEdit, setSubformEdit] = useState<{ formId: number; title: string } | null>(null);

  const load = useCallback(async () => {
    if (!processId) return;
    setLoading(true);
    try {
      const p = await api.get(`/processes/${processId}`);
      setProcess({ id: p.data.id, key: p.data.key, title: p.data.title, versions: p.data.versions });
      let vid = versionId || p.data.latest_version?.id;
      if (!vid) { setXml(''); message.info('این فرایند هنوز نسخه‌ای ندارد؛ یک فایل BPMN بارگذاری کنید'); return; }
      const v = await api.get(`/processes/versions/${vid}`);
      setVersion(v.data);
      setXml(v.data.bpmn_xml);
      setBindings(v.data.config_json?.bindings || {});
      setCalendarId(v.data.config_json?.calendarId || null);
      setMainPid(v.data.main_process_id);
    } catch (e) { message.error(extractError(e)); }
    finally { setLoading(false); }
  }, [processId, versionId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get('/forms').then((r) => setFormsList(r.data.items)).catch(() => {});
    api.get('/users', { params: { page_size: 200 } }).then((r) => setUsersList(r.data.items)).catch(() => {});
    api.get('/roles').then((r) => setRolesList(r.data.items)).catch(() => {});
    api.get('/decisions').then((r) => setDecisionsList(r.data.items)).catch(() => {});
    api.get('/calendars').then((r) => setCalendarsList(r.data.items)).catch(() => {});
  }, []);

  // انتخاب عنصر روی نمودار — از طریق ModelerHost (بدون رقابت ثبت شنونده)
  const handleSelect = useCallback((element: any) => {
    if (!element || ['bpmn:Process', 'bpmn:Collaboration'].includes(element.type)) { setSelectedEl(null); return; }
    selElRef.current = element;
    setSelectedEl({
      id: element.id, name: element.businessObject?.name || element.id, type: element.type,
      sourceType: element.source?.type || element.businessObject?.sourceRef?.$type,
    });
    setCondEval(null);
  }, []);

  // بارگذاری شرط جریان انتخاب‌شده در شرط‌ساز (فاز ۴)
  useEffect(() => {
    const el = selElRef.current;
    setCondEval(null);
    if (!selectedEl || selectedEl.type !== 'bpmn:SequenceFlow' || !isGatewayFlow(selectedEl.sourceType)) {
      setCondMode('none'); setCondGroup(null); return;
    }
    const body: string = el?.businessObject?.conditionExpression?.body || '';
    setHasCondition(!!body.trim());
    setCondManual(body);
    if (!body.trim()) {
      setCondGroup(emptyCondition()); setCondMode('visual'); return;
    }
    const r = parseCondition(body);
    if (r.structure) { setCondGroup(r.structure); setCondMode('visual'); }
    else { setCondGroup(null); setCondMode('manual'); }
    // پیشنهاد متغیرها از فرم‌های متصل
    loadVarSuggestions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEl?.id, selectedEl?.type, xml]);

  const loadVarSuggestions = useCallback(async () => {
    try {
      const fids = new Set<number>();
      Object.values(bindings || {}).forEach((b: any) => { if (b?.formDefinitionId) fids.add(Number(b.formDefinitionId)); });
      const keys = new Set<string>(['action', 'business_key']);
      await Promise.all([...fids].map(async (fid) => {
        try {
          const r = await api.get(`/forms/versions/published-by-form/${fid}`);
          (r.data.schema_json?.fields || []).forEach((f: any) => { if (f.key) keys.add(f.key); });
        } catch { /* فرم منتشرشده ندارد */ }
      }));
      setCondVarOptions([...keys]);
    } catch { /* پیشنهاد ساده */ }
  }, [bindings]);

  const applyConditionExpr = async (expr: string) => {
    const el = selElRef.current; const m = modelerRef.current;
    if (!el || !m) return;
    const modeling = m.get('modeling');
    const moddle = m.get('moddle');
    const cond = moddle.create('bpmn:FormalExpression', { body: expr });
    modeling.updateProperties(el, { conditionExpression: cond });
    setHasCondition(true);
    setCondManual(expr);
    message.success('شرط مسیر اعمال شد — برای ماندگاری، نسخه را ذخیره کنید');
  };

  const removeCondition = () => {
    const el = selElRef.current; const m = modelerRef.current;
    if (!el || !m) return;
    m.get('modeling').updateProperties(el, { conditionExpression: undefined });
    setHasCondition(false);
    setCondGroup(emptyCondition());
    setCondMode('visual');
    setCondManual('');
    message.success('شرط مسیر حذف شد');
  };

  const evalCondition = async (expr: string) => {
    let data: Record<string, unknown> = {};
    try { data = JSON.parse(condSample || '{}'); } catch { setCondEval({ ok: false, msg: 'داده نمونه JSON معتبر نیست' }); return; }
    try {
      const r = await api.post('/conditions/evaluate', { expression: expr, data });
      if (r.data.ok) setCondEval({ ok: true, result: r.data.result, msg: r.data.result ? 'شرط برقرار است (درست)' : 'شرط برقرار نیست (نادرست)' });
      else setCondEval({ ok: false, msg: r.data.errors?.join(' | ') || 'ارزیابی ممکن نشد' });
    } catch (e) { setCondEval({ ok: false, msg: extractError(e) }); }
  };

  const onModelerReady = useCallback((m: any) => {
    modelerRef.current = m;
    // دسترسی آزمون‌های E2E و اشکال‌زدایی به رجیستری عناصر نمودار
    (window as any).__bpms_modeler = m;
  }, []);

  // رنگ‌آمیزی عنصر انتخاب‌شده (فاز ۸)
  const applyElementColor = (stroke: string, fill: string) => {
    const el = selElRef.current; const m = modelerRef.current;
    if (!el || !m) return;
    m.get('modeling').setColor([el], { fill, stroke });
    message.success(`رنگ «${el.businessObject?.name || el.id}» اعمال شد — برای ماندگاری نسخه را ذخیره کنید`);
  };

  const clearElementColor = () => {
    const el = selElRef.current; const m = modelerRef.current;
    if (!el || !m) return;
    try { m.get('modeling').setColor([el], {}); } catch { /* نسخه‌های قدیمی */ }
    message.success('رنگ عنصر پاک شد');
  };

  const getXml = async (): Promise<string> => {
    if (!modelerRef.current) throw new Error('مدل جاری بارگذاری نشده است');
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

  // ساخت نسخه اول برای فرایندی که هنوز نسخه ندارد (رفع بن‌بست قبلی)
  const createFirstVersion = async () => {
    if (!xml) { message.warning('ابتدا یک فایل BPMN بارگذاری کنید'); return; }
    setSaving(true);
    try {
      const r = await api.post(`/processes/${processId}/versions`, {
        bpmn_xml: xml, main_process_id: mainPid, config_json: { bindings: {}, calendarId: null },
        change_note: 'نسخه اول از فایل بارگذاری‌شده',
      });
      message.success('نسخه اول ساخته شد — اکنون قابل طراحی و انتشار است');
      setSp({ v: String(r.data.id) });
      load();
    } catch (e) { message.error(extractError(e)); }
    finally { setSaving(false); }
  };

  const saveVersion = async (publish: boolean, changeNote: string = '', newVersionId?: number) => {
    setSaving(true);
    try {
      const content = await getXml();
      const vid = newVersionId || versionId;
      if (!vid) {
        // فرایند بدون نسخه — ساخت نسخه اول از مدل جاری
        const r = await api.post(`/processes/${processId}/versions`, {
          bpmn_xml: content, main_process_id: mainPid, config_json: { bindings, calendarId },
          change_note: changeNote || 'نسخه اول از فایل بارگذاری‌شده',
        });
        message.success('نسخه اول ساخته شد');
        setSp({ v: String(r.data.id) });
        setSaving(false);
        load();
        return;
      }
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
  const isSeqFlow = selectedEl?.type === 'bpmn:SequenceFlow';
  const condCapable = isSeqFlow && isGatewayFlow(selectedEl?.sourceType);
  const configurable = isUserTask || isServiceTask || isStart;
  const condExprPreview = (() => {
    try { return condMode === 'visual' && condGroup ? renderCondition(condGroup) : condManual; }
    catch (e) { return (e as Error).message; }
  })();

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
          <Upload beforeUpload={(f: unknown) => uploadFile(f as unknown as File)} showUploadList={false} accept=".bpmn,.xml">
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
          {version && version.status !== 'draft' && (
            <Button icon={<FileAddOutlined />} onClick={() => setNewVersionOpen(true)}>نسخه جدید از این مدل</Button>
          )}
          {!version && xml && (
            <Button type="primary" icon={<FileAddOutlined />} loading={saving} onClick={createFirstVersion}>ساخت نسخه اول از فایل بارگذاری‌شده</Button>
          )}
          {version && <Button onClick={validateNow}>اعتبارسنجی</Button>}
          {version && (
            <Button icon={<BankOutlined />} loading={saving}
              onClick={async () => {
                try {
                  const content = await getXml();
                  await api.post(`/library/processes/from-existing/${processId}`, {
                    bpmn_xml: content, main_process_id: mainPid, category: '',
                  });
                  message.success('مدل در بانک فرایندهای سازمانی ذخیره شد');
                } catch (e) { message.error(extractError(e)); }
              }}>ذخیره در بانک</Button>
          )}
        </Space>
      }
    >
      {loading && !process && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spin size="large" /></div>
      )}
      {!loading && !version && (
        <Alert type="info" showIcon style={{ marginBottom: 12 }}
          message="این فرایند هنوز نسخه‌ای ندارد"
          description="یک فایل BPMN بارگذاری کنید (دکمه «باز کردن فایل BPMN» در نوار بالا) و سپس «ساخت نسخه اول» را بزنید. پس از آن مدل قابل طراحی، تنظیم فرم/مسئول و انتشار خواهد بود." />
      )}
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
            <ModelerHost xml={xml} onReady={onModelerReady} onSelect={handleSelect} onParsed={(p) => { setProcs(p); if (!mainPid && p.length) setMainPid((p.find((x: any) => x.isExecutable) || p[0]).id); }} />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              برای تنظیم فرم/مسئول/نتیجه، فعالیت موردنظر را روی نمودار انتخاب کنید تا پنل تنظیمات باز شود.
            </Typography.Text>
          </Col>
          <Col span={6}>
            <Card size="small" title={<span><SettingOutlined /> تنظیمات فعالیت انتخابی</span>} styles={{ body: { minHeight: 300 } }}>
              {!selectedEl && <Alert type="info" message="ابتدا یک عنصر را روی نمودار انتخاب کنید" />}
              {selectedEl && !configurable && !condCapable && (
                <Alert type="info" message={`عنصر «${selectedEl.name}» (${selectedEl.type}) تنظیم خاصی ندارد`} />
              )}
              {selectedEl && isSeqFlow && !condCapable && (
                <Alert type="info" message="شرط فقط روی جریان‌های خروجی از دروازه انحصاری/فراگیر اعمال می‌شود" />
              )}
              {selectedEl && condCapable && (
                <div data-testid="condition-section">
                  <Divider style={{ margin: '4px 0 10px' }} />
                  <Space direction="vertical" style={{ width: '100%' }} size={6}>
                    <Space wrap>
                      <FilterOutlined />
                      <Typography.Text strong>شرط مسیر (شرط‌ساز بصری)</Typography.Text>
                      {hasCondition && <Tag color="blue">شرط تعریف‌شده</Tag>}
                    </Space>
                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                      جریان «{selectedEl.name}» از دروازه شرطی خارج می‌شود — شرط پایتونی معادل تولید و روی مدل اعمال می‌شود.
                    </Typography.Text>
                    {condMode === 'visual' && condGroup && (
                      <>
                        <ConditionBuilder value={condGroup} varOptions={condVarOptions} onChange={setCondGroup} />
                        <div>
                          <Typography.Text type="secondary" style={{ fontSize: 11 }}>عبارت تولیدشده:</Typography.Text>
                          <pre data-testid="cond-preview" className="mono" style={{ background: '#0f172a', color: '#e2e8f0', borderRadius: 6, padding: 8, fontSize: 11, whiteSpace: 'pre-wrap', direction: 'ltr', textAlign: 'left' }}>{condExprPreview}</pre>
                        </div>
                        <Space wrap size={6}>
                          <Button size="small" type="primary" icon={<SettingOutlined />} data-testid="apply-condition"
                            disabled={!condGroup.items.length}
                            onClick={() => { try { applyConditionExpr(renderCondition(condGroup)); } catch (e) { message.error((e as Error).message); } }}>
                            اعمال شرط روی جریان
                          </Button>
                          <Button size="small" icon={<PlayCircleOutlined />} onClick={() => evalCondition(condExprPreview)}>
                            آزمایش شرط
                          </Button>
                          {hasCondition && (
                            <Popconfirm title="حذف شرط این جریان؟" onConfirm={removeCondition} okText="حذف" cancelText="انصراف">
                              <Button size="small" danger icon={<DeleteOutlined />}>حذف شرط</Button>
                            </Popconfirm>
                          )}
                        </Space>
                      </>
                    )}
                    {condMode === 'manual' && (
                      <Alert type="warning" showIcon
                        message="این عبارت در شرط‌ساز بصری پشتیبانی نمی‌شود — حالت دستی"
                        description={
                          <Space direction="vertical" style={{ width: '100%' }}>
                            <Input.TextArea className="mono" rows={3} style={{ direction: 'ltr', textAlign: 'left' }}
                              value={condManual} onChange={(e) => setCondManual(e.target.value)} />
                            <Button size="small" type="primary" onClick={() => applyConditionExpr(condManual)}>اعمال عبارت دستی</Button>
                          </Space>
                        } />
                    )}
                    <Input.TextArea
                      rows={2} value={condSample} onChange={(e) => setCondSample(e.target.value)}
                      placeholder='داده نمونه JSON برای آزمایش شرط — مثال: {"action": "approve"}'
                      style={{ direction: 'ltr', textAlign: 'left', fontSize: 11 }}
                    />
                    {condEval && (
                      <Alert type={condEval.ok ? (condEval.result ? 'success' : 'warning') : 'error'}
                        showIcon message={condEval.msg} />
                    )}
                  </Space>
                </div>
              )}
              {selectedEl && (
                <div style={{ marginBottom: 10 }} data-testid="color-section">
                  <Divider style={{ margin: '4px 0 10px' }} />
                  <Space wrap size={4}>
                    <BgColorsOutlined />
                    <Typography.Text strong style={{ fontSize: 12 }}>رنگ‌آمیزی عنصر</Typography.Text>
                  </Space>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                    {PROCESS_COLORS.map((c) => (
                      <button
                        key={c.name}
                        title={c.name}
                        onClick={() => applyElementColor(c.stroke, c.fill)}
                        style={{
                          width: 26, height: 22, borderRadius: 4, cursor: 'pointer',
                          border: `2px solid ${c.stroke}`, background: c.fill, padding: 0,
                        }}
                      />
                    ))}
                  </div>
                  <Space style={{ marginTop: 6 }} size={6}>
                    <ColorPicker size="small" showText disabledFormat
                      onChange={(c) => {
                        const hex = c.toHexString();
                        applyElementColor(hex, hex + '33');
                      }} />
                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>رنگ سفارشی</Typography.Text>
                    <Button size="small" type="link" onClick={clearElementColor}>پاک‌کردن رنگ</Button>
                  </Space>
                </div>
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
          if (!modelerRef.current) {
            message.error('مدل جاری بارگذاری نشده است — ابتدا فایل BPMN را باز کنید');
            return;
          }
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

// میزبان Modeler با لود XML — جدا برای مدیریت lifecycle؛ شنونده انتخاب در همین‌جا ثبت می‌شود
function ModelerHost({ xml, onReady, onSelect, onParsed }: {
  xml: string; onReady: (m: any) => void; onSelect: (element: any) => void; onParsed: (p: any[]) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const mRef = useRef<any>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!ref.current) return;
    import('bpmn-js/lib/Modeler').then((Mod) => {
      const m = new Mod.default({
        container: ref.current as HTMLElement,
        keyboard: { bindTo: document },
        // پالت کامل BPMN — همه رویدادها/وظایف/دروازه‌ها/داده‌ها (فاز ۸)
        additionalModules: [BpmsCompletePaletteModule],
      });
      mRef.current = m;
      onReady(m);
      // شنونده انتخاب روی همان نمونه زنده — بدون وابستگی به ترتیب mount والد
      m.on('selection.changed', ({ newSelection }: any) => {
        onSelect(newSelection && newSelection.length ? newSelection[0] : null);
      });
      setReady(true);
    });
    return () => { mRef.current?.destroy(); mRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
