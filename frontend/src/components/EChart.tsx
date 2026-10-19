// نمودارهای تعاملی — پوشش سبک ECharts برای React (فاز ۷)
// مقداردهی اولیه، تمریر (hover)، تغییر اندازه واکنش‌گرا و آزادسازی منابع
import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';

interface EChartProps {
  option: EChartsOption;
  height?: number | string;
  testid?: string;
  onClick?: (params: echarts.ECElementEvent) => void;
}

export const CHART_COLORS = {
  blue: '#3b82f6',
  green: '#10b981',
  red: '#ef4444',
  orange: '#f59e0b',
  slate: '#94a3b8',
  purple: '#8b5cf6',
};

export const FONT_FA = 'Vazirmatn, Tahoma, sans-serif';

/** قلم و جهت فارسی پیش‌فرض همه نمودارها */
export function baseText(extra: Record<string, unknown> = {}) {
  return { fontFamily: FONT_FA, ...extra };
}

export default function EChart({ option, height = 320, testid, onClick }: EChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const clickRef = useRef(onClick);
  clickRef.current = onClick;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = echarts.init(el, undefined, { renderer: 'canvas' });
    chartRef.current = chart;
    chart.on('click', (p) => clickRef.current?.(p));
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  return <div ref={ref} data-testid={testid} style={{ width: '100%', height }} />;
}
