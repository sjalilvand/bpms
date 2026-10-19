// صفحه میزبان فرم‌ساز — بارگذاری نسخه و هدایت به Designer
import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { Spin } from 'antd';
import { api } from '../api/client';
import FormDesigner from '../components/FormDesigner';
import type { FormSchema } from '../lib/formSchema';

export default function FormDesignerPage() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const formId = Number(id || 0);
  const versionId = Number(sp.get('v') || 0);
  const [data, setData] = useState<{ form: any; version: any } | null>(null);

  useEffect(() => {
    if (!formId || !versionId) return;
    api.get(`/forms/versions/${versionId}`).then((r) => {
      setData({ form: r.data.form, version: r.data });
    }).catch(() => setData(null));
  }, [formId, versionId]);

  if (!formId || !versionId || !data) return <Spin size="large" style={{ display: 'block', margin: '120px auto' }} />;

  return (
    <FormDesigner
      formId={formId}
      formTitle={data.form.title}
      versionId={versionId}
      versionStatus={data.version.status}
      initialSchema={data.version.schema_json as FormSchema}
      changeNote={data.version.change_note}
      onSaved={() => window.location.reload()}
    />
  );
}
