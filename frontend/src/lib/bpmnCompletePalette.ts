// پالت کامل BPMN — جایگزین پالت پیش‌فرض bpmn-js با کل عناصر استاندارد (فاز ۸)
// رویدادها (شروع/میانی/پایان/مرزی با همه تعریف‌ها)، وظایف (۷ نوع + فراخوانی + زیرفرایند + تراکنش)،
// دروازه‌ها (۵ نوع)، داده‌ها، حاشیه‌نویسی، گروه و استخر — همه با درگ‌اند‌دراپ بومی bpmn-js.
//
// استفاده: Modeler با additionalModules={[ BpmsCompletePaletteModule ]}

const LOW_PRIORITY = 500;

interface EntryAction {
  dragstart: (event: Event) => void;
  click: (event: Event) => void;
}

interface PaletteEntry {
  group?: string;
  className?: string;
  title?: string;
  separator?: boolean;
  action?: EntryAction;
}

function createAction(
  type: string, group: string, className: string, title: string,
  options: Record<string, unknown> | undefined, create: any, elementFactory: any,
): PaletteEntry {
  function createListener(event: Event) {
    const shape = elementFactory.createShape({ type, ...(options || {}) });
    create.start(event, shape);
  }
  return {
    group,
    className,
    title,
    action: {
      dragstart: createListener,
      click: createListener,
    },
  };
}

export class BpmsCompletePaletteProvider {
  private _palette: any;
  private _create: any;
  private _elementFactory: any;
  private _spaceTool: any;
  private _lassoTool: any;
  private _handTool: any;
  private _globalConnect: any;

  constructor(palette: any, create: any, elementFactory: any,
              spaceTool: any, lassoTool: any, handTool: any, globalConnect: any) {
    this._palette = palette;
    this._create = create;
    this._elementFactory = elementFactory;
    this._spaceTool = spaceTool;
    this._lassoTool = lassoTool;
    this._handTool = handTool;
    this._globalConnect = globalConnect;
    palette.registerProvider(LOW_PRIORITY, this);
  }

  getPaletteEntries(): Record<string, PaletteEntry> {
    const create = this._create;
    const elementFactory = this._elementFactory;
    const spaceTool = this._spaceTool;
    const lassoTool = this._lassoTool;
    const handTool = this._handTool;
    const globalConnect = this._globalConnect;

    const act = (type: string, group: string, className: string, title: string,
                 options?: Record<string, unknown>) =>
      createAction(type, group, className, title, options, create, elementFactory);

    const tool = (fn: () => void): EntryAction => ({ dragstart: fn, click: fn });

    return {
      'hand-tool': {
        group: 'tools',
        className: 'bpmn-icon-hand-tool',
        title: 'جابه‌جایی بوم',
        action: tool(() => handTool.activateHandtool()),
      },
      'lasso-tool': {
        group: 'tools',
        className: 'bpmn-icon-lasso-tool',
        title: 'انتخاب چندگانه',
        action: tool(() => lassoTool.activateSelection()),
      },
      'space-tool': {
        group: 'tools',
        className: 'bpmn-icon-space-tool',
        title: 'ایجاد فاصله',
        action: tool(() => spaceTool.activateSelection()),
      },
      'global-connect-tool': {
        group: 'tools',
        className: 'bpmn-icon-connection-multi',
        title: 'اتصال سراسری (جریان توالی/پیام)',
        action: tool(() => globalConnect.toggle()),
      },
      'separator-tools': { separator: true },

      // ---------- رویدادهای شروع ----------
      'start-none': act('bpmn:StartEvent', 'event-start', 'bpmn-icon-start-event-none', 'رویداد شروع (ساده)'),
      'start-message': act('bpmn:StartEvent', 'event-start', 'bpmn-icon-start-event-message', 'شروع پیامی', { eventDefinitionType: 'bpmn:MessageEventDefinition' }),
      'start-timer': act('bpmn:StartEvent', 'event-start', 'bpmn-icon-start-event-timer', 'شروع زمان‌بندی‌شده', { eventDefinitionType: 'bpmn:TimerEventDefinition' }),
      'start-signal': act('bpmn:StartEvent', 'event-start', 'bpmn-icon-start-event-signal', 'شروع سیگنالی', { eventDefinitionType: 'bpmn:SignalEventDefinition' }),
      'start-conditional': act('bpmn:StartEvent', 'event-start', 'bpmn-icon-start-event-conditional', 'شروع شرطی', { eventDefinitionType: 'bpmn:ConditionalEventDefinition' }),
      'start-escalation': act('bpmn:StartEvent', 'event-start', 'bpmn-icon-start-event-escalation', 'شروع تشدید', { eventDefinitionType: 'bpmn:EscalationEventDefinition' }),
      'start-error': act('bpmn:StartEvent', 'event-start', 'bpmn-icon-start-event-error', 'شروع خطا', { eventDefinitionType: 'bpmn:ErrorEventDefinition' }),
      'start-compensation': act('bpmn:StartEvent', 'event-start', 'bpmn-icon-start-event-compensation', 'شروع جبرانی', { eventDefinitionType: 'bpmn:CompensationEventDefinition' }),
      'separator-start': { separator: true },

      // ---------- رویدادهای میانی ----------
      'catch-none': act('bpmn:IntermediateCatchEvent', 'event-intermediate', 'bpmn-icon-intermediate-event-none', 'رویداد میانی (دریافت ساده)'),
      'catch-message': act('bpmn:IntermediateCatchEvent', 'event-intermediate', 'bpmn-icon-intermediate-event-catch-message', 'دریافت پیام', { eventDefinitionType: 'bpmn:MessageEventDefinition' }),
      'catch-timer': act('bpmn:IntermediateCatchEvent', 'event-intermediate', 'bpmn-icon-intermediate-event-catch-timer', 'انتظار زمانی', { eventDefinitionType: 'bpmn:TimerEventDefinition' }),
      'catch-signal': act('bpmn:IntermediateCatchEvent', 'event-intermediate', 'bpmn-icon-intermediate-event-catch-signal', 'دریافت سیگنال', { eventDefinitionType: 'bpmn:SignalEventDefinition' }),
      'catch-conditional': act('bpmn:IntermediateCatchEvent', 'event-intermediate', 'bpmn-icon-intermediate-event-catch-conditional', 'رویداد شرطی', { eventDefinitionType: 'bpmn:ConditionalEventDefinition' }),
      'catch-link': act('bpmn:IntermediateCatchEvent', 'event-intermediate', 'bpmn-icon-intermediate-event-catch-link', 'پیوند (Link)', { eventDefinitionType: 'bpmn:LinkEventDefinition' }),
      'throw-none': act('bpmn:IntermediateThrowEvent', 'event-intermediate', 'bpmn-icon-intermediate-event-none', 'رویداد میانی (ارسال ساده)'),
      'throw-message': act('bpmn:IntermediateThrowEvent', 'event-intermediate', 'bpmn-icon-intermediate-event-throw-message', 'ارسال پیام', { eventDefinitionType: 'bpmn:MessageEventDefinition' }),
      'throw-signal': act('bpmn:IntermediateThrowEvent', 'event-intermediate', 'bpmn-icon-intermediate-event-throw-signal', 'ارسال سیگنال', { eventDefinitionType: 'bpmn:SignalEventDefinition' }),
      'throw-escalation': act('bpmn:IntermediateThrowEvent', 'event-intermediate', 'bpmn-icon-intermediate-event-throw-escalation', 'ارسال تشدید', { eventDefinitionType: 'bpmn:EscalationEventDefinition' }),
      'throw-compensation': act('bpmn:IntermediateThrowEvent', 'event-intermediate', 'bpmn-icon-intermediate-event-throw-compensation', 'ارسال جبرانی', { eventDefinitionType: 'bpmn:CompensationEventDefinition' }),
      'separator-intermediate': { separator: true },

      // ---------- رویدادهای مرزی (با رهاکردن روی فعالیت متصل می‌شوند) ----------
      'boundary-message': act('bpmn:BoundaryEvent', 'event-boundary', 'bpmn-icon-boundary-event-message', 'مرزی پیامی', { eventDefinitionType: 'bpmn:MessageEventDefinition' }),
      'boundary-timer': act('bpmn:BoundaryEvent', 'event-boundary', 'bpmn-icon-boundary-event-timer', 'مرزی زمانی', { eventDefinitionType: 'bpmn:TimerEventDefinition' }),
      'boundary-error': act('bpmn:BoundaryEvent', 'event-boundary', 'bpmn-icon-boundary-event-error', 'مرزی خطا', { eventDefinitionType: 'bpmn:ErrorEventDefinition' }),
      'boundary-escalation': act('bpmn:BoundaryEvent', 'event-boundary', 'bpmn-icon-boundary-event-escalation', 'مرزی تشدید', { eventDefinitionType: 'bpmn:EscalationEventDefinition' }),
      'boundary-signal': act('bpmn:BoundaryEvent', 'event-boundary', 'bpmn-icon-boundary-event-signal', 'مرزی سیگنالی', { eventDefinitionType: 'bpmn:SignalEventDefinition' }),
      'boundary-cancel': act('bpmn:BoundaryEvent', 'event-boundary', 'bpmn-icon-boundary-event-cancel', 'مرزی لغو', { eventDefinitionType: 'bpmn:CancelEventDefinition' }),
      'boundary-conditional': act('bpmn:BoundaryEvent', 'event-boundary', 'bpmn-icon-boundary-event-conditional', 'مرزی شرطی', { eventDefinitionType: 'bpmn:ConditionalEventDefinition' }),
      'boundary-compensation': act('bpmn:BoundaryEvent', 'event-boundary', 'bpmn-icon-boundary-event-compensation', 'مرزی جبرانی', { eventDefinitionType: 'bpmn:CompensationEventDefinition' }),
      'separator-boundary': { separator: true },

      // ---------- رویدادهای پایان ----------
      'end-none': act('bpmn:EndEvent', 'event-end', 'bpmn-icon-end-event-none', 'رویداد پایان (ساده)'),
      'end-message': act('bpmn:EndEvent', 'event-end', 'bpmn-icon-end-event-message', 'پایان پیامی', { eventDefinitionType: 'bpmn:MessageEventDefinition' }),
      'end-error': act('bpmn:EndEvent', 'event-end', 'bpmn-icon-end-event-error', 'پایان خطا', { eventDefinitionType: 'bpmn:ErrorEventDefinition' }),
      'end-escalation': act('bpmn:EndEvent', 'event-end', 'bpmn-icon-end-event-escalation', 'پایان تشدید', { eventDefinitionType: 'bpmn:EscalationEventDefinition' }),
      'end-terminate': act('bpmn:EndEvent', 'event-end', 'bpmn-icon-end-event-terminate', 'پایان فوری (Terminate)', { eventDefinitionType: 'bpmn:TerminateEventDefinition' }),
      'end-signal': act('bpmn:EndEvent', 'event-end', 'bpmn-icon-end-event-signal', 'پایان سیگنالی', { eventDefinitionType: 'bpmn:SignalEventDefinition' }),
      'end-compensation': act('bpmn:EndEvent', 'event-end', 'bpmn-icon-end-event-compensation', 'پایان جبرانی', { eventDefinitionType: 'bpmn:CompensationEventDefinition' }),
      'end-cancel': act('bpmn:EndEvent', 'event-end', 'bpmn-icon-end-event-cancel', 'پایان لغو', { eventDefinitionType: 'bpmn:CancelEventDefinition' }),
      'separator-end': { separator: true },

      // ---------- فعالیت‌ها ----------
      'task-user': act('bpmn:UserTask', 'activity', 'bpmn-icon-user-task', 'وظیفه کاربر (فرم/مسئول)'),
      'task-service': act('bpmn:ServiceTask', 'activity', 'bpmn-icon-service-task', 'وظیفه سرویس (کانکتور)'),
      'task-script': act('bpmn:ScriptTask', 'activity', 'bpmn-icon-script-task', 'وظیفه اسکریپت'),
      'task-send': act('bpmn:SendTask', 'activity', 'bpmn-icon-send-task', 'وظیفه ارسال'),
      'task-receive': act('bpmn:ReceiveTask', 'activity', 'bpmn-icon-receive-task', 'وظیفه دریافت'),
      'task-manual': act('bpmn:ManualTask', 'activity', 'bpmn-icon-manual-task', 'وظیفه دستی'),
      'task-rule': act('bpmn:BusinessRuleTask', 'activity', 'bpmn-icon-business-rule-task', 'وظیفه قواعد کسب‌وکار'),
      'call-activity': act('bpmn:CallActivity', 'activity', 'bpmn-icon-call-activity', 'فعالیت فراخوانی (زیرفرایند)'),
      'subprocess-expanded': act('bpmn:SubProcess', 'activity', 'bpmn-icon-subprocess-expanded', 'زیرفرایند بازشده', { isExpanded: true }),
      'subprocess-collapsed': act('bpmn:SubProcess', 'activity', 'bpmn-icon-subprocess-collapsed', 'زیرفرایند جمع‌شده', { isExpanded: false }),
      'transaction': act('bpmn:Transaction', 'activity', 'bpmn-icon-transaction', 'تراکنش (بازگشت‌پذیر)', { isExpanded: true }),
      'event-subprocess': act('bpmn:SubProcess', 'activity', 'bpmn-icon-event-subprocess', 'زیرفرایند رویدادی', { triggeredByEvent: true }),
      'separator-activity': { separator: true },

      // ---------- دروازه‌ها ----------
      'gateway-xor': act('bpmn:ExclusiveGateway', 'gateway', 'bpmn-icon-gateway-xor', 'دروازه انحصاری (XOR)'),
      'gateway-parallel': act('bpmn:ParallelGateway', 'gateway', 'bpmn-icon-gateway-parallel', 'دروازه موازی (AND)'),
      'gateway-inclusive': act('bpmn:InclusiveGateway', 'gateway', 'bpmn-icon-gateway-inclusive', 'دروازه فراگیر (OR)'),
      'gateway-complex': act('bpmn:ComplexGateway', 'gateway', 'bpmn-icon-gateway-complex', 'دروازه پیچیده'),
      'gateway-event': act('bpmn:EventBasedGateway', 'gateway', 'bpmn-icon-gateway-event', 'دروازه رویدادمحور'),
      'separator-gateway': { separator: true },

      // ---------- داده و حاشیه‌نویسی ----------
      'data-object': act('bpmn:DataObjectReference', 'data', 'bpmn-icon-data-object', 'شیء داده'),
      'data-store': act('bpmn:DataStoreReference', 'data', 'bpmn-icon-data-store', 'مخزن داده'),
      'group': act('bpmn:Group', 'data', 'bpmn-icon-group', 'گروه‌بندی'),
      'text-annotation': act('bpmn:TextAnnotation', 'data', 'bpmn-icon-text-annotation', 'حاشیه‌نویسی متن'),
      'separator-data': { separator: true },

      // ---------- همکاری ----------
      'participant': act('bpmn:Participant', 'collaboration', 'bpmn-icon-participant', 'استخر/نقش سازمانی', { isExpanded: true }),
    };
  }
}

(BpmsCompletePaletteProvider as any).$inject = [
  'palette', 'create', 'elementFactory',
  'spaceTool', 'lassoTool', 'handTool', 'globalConnect',
];

// ثبت ماژول به‌عنوان additionalModules در bpmn-js
export const BpmsCompletePaletteModule: Record<string, unknown> = {
  __init__: ['bpmsCompletePalette'],
  bpmsCompletePalette: ['type', BpmsCompletePaletteProvider],
};
