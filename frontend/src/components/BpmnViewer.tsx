// نمایشگر BPMN با نشانگرهای وضعیت زنده (فعال/انجام‌شده/خطا)
import React, { useEffect, useRef } from 'react';
import BpmnJS from 'bpmn-js/lib/Modeler';

interface Props {
  xml: string;
  active?: string[];
  completed?: string[];
  error?: string[];
  onModelerReady?: (modeler: any) => void;
  editable?: boolean;
}

export default function BpmnViewer({ xml, active = [], completed = [], error = [], onModelerReady, editable }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const modelerRef = useRef<any>(null);

  useEffect(() => {
    if (!ref.current) return;
    const modeler = new BpmnJS({ container: ref.current });
    modelerRef.current = modeler;
    onModelerReady?.(modeler);
    return () => { modeler.destroy(); modelerRef.current = null; };
  }, []);

  useEffect(() => {
    const modeler = modelerRef.current;
    if (!modeler || !xml) return;
    modeler.importXML(xml).then(({ warnings }: any) => {
      const canvas = modeler.get('canvas');
      canvas.zoom('fit-viewport');
      const mark = (ids: string[], cls: string) => ids.forEach((id) => {
        try { canvas.addMarker(id, cls); } catch { /* عنصر ناموجود */ }
      });
      mark(completed, 'bpms-completed');
      mark(active, 'bpms-active');
      mark(error, 'bpms-error');
    }).catch((e: Error) => console.error('import XML failed:', e));
  }, [xml, JSON.stringify(active), JSON.stringify(completed), JSON.stringify(error)]);

  return <div ref={ref} className="bpmn-canvas" style={{ height: editable ? 'calc(100vh - 230px)' : 420 }} />;
}
