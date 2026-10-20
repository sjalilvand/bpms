// صفحه میزبان فرم‌ساز — بارگذاری نسخه (با انتخاب خودکار آخرین نسخه) و هدایت به Designer
import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { Button, Empty, Spin, Result } from 'antd';
import { api } from '../api/client';
import FormDesigner from '../components/FormDesigner';
import type { FormSchema } from '../lib/formSchema';

export default function FormDesignerPage() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const formId = Number(id || 0);
  const versionId = Number(sp.get('v') || 0);
  const [data, setData] = useState<{ form: any; version: any } | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error' | 'empty'>('loading');

  useEffect(() => {
    if (!formId) return;
    let alive = true;
    setStatus('loading');
    (async () => {
      try {
        if (versionId) {
          const r = await api.get(`/forms/versions/${versionId}`);
          if (!alive) return;
          setData({ form: r.data.form, version: r.data });
          setStatus('ready');
        } else {
          // بدون پارامتر v — آخرین نسخه فرم به‌طور خودکار باز می‌شود
          const r = await api.get(`/forms/${formId}`);
          const latest = r.data.latest_version;
          if (!alive) return;
          if (!latest?.id) { setStatus('empty'); return; }
          const v = await api.get(`/forms/versions/${latest.id}`);
          if (!alive) return;
          setData({ form: r.data, version: v.data });
          setStatus('ready');
        }
      } catch {
        if (alive) setStatus('error');
      }
    })();
    return () => { alive = false; };
  }, [formId, versionId]);

  if (!formId || status === 'error') {
    return (
      <Result
        status="404"
        title="فرم یا نسخه یافت نشد"
        subTitle="ممکن است نسخه حذف شده باشد — از صفحه فرم‌ها دوباره وارد شوید."
        extra={<Button type="primary" href="/forms">بازگشت به فهرست فرم‌ها</Button>}
      />
    );
  }
  if (status === 'empty') {
    return <Empty description="این فرم هنوز هیچ نسخه‌ای ندارد" style={{ marginTop: 80 }} />;
  }
  if (status !== 'ready' || !data) {
    return <Spin size="large" style={{ display: 'block', margin: '120px auto' }} />;
  }

  return (
    <FormDesigner
      formId={formId}
      formTitle={data.form.title}
      versionId={data.version.id}
      versionStatus={data.version.status}
      initialSchema={data.version.schema_json as FormSchema}
      changeNote={data.version.change_note}
      onSaved={() => window.location.reload()}
    />
  );
}
