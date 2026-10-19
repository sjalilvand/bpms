// کلاینت API — axios با قالب خطای یکسان سرور
import axios from 'axios';

export const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('bpms_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401 && !location.pathname.startsWith('/login')) {
      localStorage.removeItem('bpms_token');
      localStorage.removeItem('bpms_user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  },
);

export function extractError(err: unknown): string {
  const e = err as { response?: { data?: { error?: { message?: string; errors?: { message?: string }[] } } } };
  const data = e?.response?.data;
  if (!data?.error) return 'خطای ناشناخته رخ داد';
  const base = data.error.message || '';
  const fieldErrors = data.error.errors;
  if (Array.isArray(fieldErrors) && fieldErrors.length) {
    return base + ' — ' + fieldErrors.map((x) => x.message).join('؛ ');
  }
  return base || 'خطا در پردازش درخواست';
}

// ---------- API رابط‌های تایپ‌دار ----------
export interface UserInfo {
  id: number;
  username: string;
  full_name: string;
  is_superadmin: boolean;
  roles: { id: number; code: string; title: string; permissions: string[] }[];
  org_unit_id?: number | null;
}

export interface Paged<T> {
  items: T[];
  total: number;
}

export interface FormRow {
  id: number;
  key: string;
  title: string;
  description: string;
  latest_version: VersionRow | null;
  published_version: VersionRow | null;
}

export interface VersionRow {
  id: number;
  form_id?: number;
  definition_id?: number;
  version: number;
  status: string;
  change_note?: string;
  created_at?: string;
  published_at?: string;
  schema_json?: FormSchemaT;
  bpmn_xml?: string;
  config_json?: ProcessConfig;
  main_process_id?: string;
}

// نوع فرم را از formSchema می‌آوریم تا چرخه ایجاد نشود
import type { FormSchema as FormSchemaT } from '../lib/formSchema';

export interface ProcessConfig {
  bindings: Record<string, TaskBinding>;
}

export interface TaskBinding {
  formDefinitionId?: number | null;
  assigneeType?: 'user' | 'role' | 'field' | 'self' | '';
  assigneeValue?: string | number | null;
  results?: { value: string; label: string }[];
  dueHours?: number | null;
  connector?: string;
}

export interface ProcessRow {
  id: number;
  key: string;
  title: string;
  description: string;
  latest_version: VersionRow | null;
  published_version: VersionRow | null;
}

export interface TaskRow {
  id: number;
  instance_id: number;
  name: string;
  spec_id: string;
  status: string;
  assignee_id: number | null;
  candidate_role: string | null;
  claimed_by_id: number | null;
  due_at: string | null;
  created_at_jalali?: string | null;
  result?: string | null;
  comment?: string | null;
  form_version_id: number | null;
  instance: {
    id: number;
    title: string;
    business_key: string | null;
    status: string;
    started_by_id: number;
    process_title: string | null;
    process_id: number | null;
  };
}

export interface InstanceRow {
  id: number;
  title: string;
  business_key: string | null;
  status: string;
  process: { id: number; title: string; key: string } | null;
  version: number;
  started_by_id: number;
  started_by?: string;
  started_at_jalali?: string | null;
  open_tasks?: number;
}

export interface InstanceDetailT extends InstanceRow {
  version_id: number;
  tasks: {
    id: number; spec_id: string; name: string; status: string;
    assignee_id: number | null; assignee: string | null; candidate_role: string | null;
    result: string | null; comment: string | null;
    completed_at: string | null;
  }[];
  history: {
    id: number; event_type: string; spec_id: string | null; task_name: string | null;
    actor: string | null; comment: string | null; detail: Record<string, unknown> | null;
    created_at_jalali: string | null;
  }[];
  incidents: { id: number; spec_id: string | null; message: string; created_at: string | null }[];
}
