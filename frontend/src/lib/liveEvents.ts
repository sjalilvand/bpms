// رویدادهای زنده (SSE فاز ۳) — اتصال پایدار با اتصال مجدد خودکار
import { useEffect, useRef } from 'react';

export interface LiveEvent {
  type: 'notification' | 'instance' | 'sla' | 'hello' | string;
  data: Record<string, unknown>;
  ts?: string;
}

// نام رویدادهای سفارشی بین صفحه‌ها (window events)
export const EVT_INBOX_REFRESH = 'bpms:inbox-refresh';
export const EVT_INSTANCE_REFRESH = 'bpms:instance-refresh';
export const EVT_NOTIFICATION = 'bpms:notification';

export interface LiveEventsOptions {
  onEvent?: (ev: LiveEvent) => void;
  enabled?: boolean;
}

/**
 * اتصال به جریان رویداد سرور (Server-Sent Events).
 * - توکن از localStorage خوانده می‌شود (EventSource امکان هدر ندارد).
 * - در صورت قطع شدن، با فاصله فزاینده تا ۳۰ ثانیه دوباره وصل می‌شود.
 * - پشتیبانی‌نشدن EventSource بی‌خطر است (رابط کاربری به نظرسنجی دوره‌ای بازمی‌گردد).
 */
export function useLiveEvents({ onEvent, enabled = true }: LiveEventsOptions) {
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    if (!enabled || typeof window === 'undefined' || typeof EventSource === 'undefined') return;
    const token = localStorage.getItem('bpms_token');
    if (!token) return;

    let es: EventSource | null = null;
    let retry = 0;
    let closed = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      if (closed) return;
      es = new EventSource(`/api/v1/events/stream?token=${encodeURIComponent(token)}`);
      const types = ['hello', 'notification', 'instance', 'sla'];
      for (const t of types) {
        es.addEventListener(t, (e: MessageEvent) => {
          retry = 0; // اتصال سالم است
          try {
            const data = JSON.parse(e.data || '{}');
            handlerRef.current?.({ type: t, data });
          } catch { /* ignore */ }
        });
      }
      es.onerror = () => {
        es?.close();
        if (closed) return;
        retry += 1;
        const delay = Math.min(30_000, 1_000 * Math.pow(2, Math.min(retry, 5)));
        timer = setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      es?.close();
    };
  }, [enabled]);
}

/** ارسال رویداد داخلی برای به‌روزرسانی صفحه‌ها */
export function dispatchUiEvent(name: string, detail?: unknown) {
  window.dispatchEvent(new CustomEvent(name, { detail }));
}
