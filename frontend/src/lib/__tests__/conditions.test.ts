// آزمون‌های شرط‌ساز بصری — قرینه آزمون‌های بک‌اند (test_conditions.py)
import { describe, expect, it } from 'vitest';
import {
  coerceValue, emptyCondition, parseCondition, renderCondition,
  CondParseError, CondGroup,
} from '../conditions';

describe('پارسر شرط (آینه بک‌اند)', () => {
  it('مقایسه ساده', () => {
    const r = parseCondition("action == 'approve'");
    expect(r.error).toBeNull();
    expect(r.structure).toEqual({
      combinator: 'and',
      items: [{ kind: 'compare', field: 'action', op: 'eq', value: 'approve' }],
    });
  });

  it('ترکیب و (and)', () => {
    const r = parseCondition("total_amount >= 1000000 and priority == 'high'");
    expect(r.structure?.combinator).toBe('and');
    expect(r.structure?.items).toHaveLength(2);
    expect((r.structure!.items[0] as any).op).toBe('ge');
  });

  it('ترکیب یا (or) در سطح بالا', () => {
    const r = parseCondition("priority == 'high' or priority == 'normal'");
    expect(r.structure?.combinator).toBe('or');
    expect(r.structure?.items).toHaveLength(2);
  });

  it('گروه پرانتزی تودرتو', () => {
    const r = parseCondition("total_amount > 100 and (unit == 'IT' or unit == 'FIN')");
    expect(r.structure!.items).toHaveLength(2);
    expect((r.structure!.items[1] as CondGroup).combinator).toBe('or');
  });

  it('عملگر in و not in', () => {
    const r = parseCondition("status in ['new', 'open']");
    expect((r.structure!.items[0] as any).op).toBe('in');
    expect((r.structure!.items[0] as any).value).toEqual(['new', 'open']);
    const r2 = parseCondition("status not in ['closed']");
    expect((r2.structure!.items[0] as any).op).toBe('not_in');
  });

  it('الگوی contains', () => {
    const r = parseCondition("'urgent' in tags");
    expect((r.structure!.items[0] as any)).toMatchObject({ field: 'tags', op: 'contains', value: 'urgent' });
  });

  it('خالی است / خالی نیست (is None / is not None)', () => {
    expect((parseCondition('reviewer is None').structure!.items[0] as any).op).toBe('empty');
    expect((parseCondition('reviewer is not None').structure!.items[0] as any).op).toBe('not_empty');
    expect((parseCondition('manager_id != None').structure!.items[0] as any).op).toBe('not_empty');
  });

  it('نفی شرط', () => {
    const r = parseCondition('not (approved == True)');
    expect((r.structure!.items[0] as any).negate).toBe(true);
  });

  it('مسیر نقطه‌دار', () => {
    const r = parseCondition('order.total > 1000');
    expect((r.structure!.items[0] as any).field).toBe('order.total');
  });

  it('خطا در عبارت نامعتبر → حالت دستی', () => {
    expect(parseCondition('action ==').error).not.toBeNull();
    expect(parseCondition("__import__('os').system('x')").error).not.toBeNull();
  });
});

describe('رندر شرط', () => {
  it('round-trip ساده', () => {
    const g: CondGroup = { combinator: 'and', items: [{ kind: 'compare', field: 'action', op: 'eq', value: 'approve' }] };
    expect(renderCondition(g)).toBe("action == 'approve'");
  });

  it('round-trip پیچیده با گروه', () => {
    const g: CondGroup = {
      combinator: 'and',
      items: [
        { kind: 'compare', field: 'total_amount', op: 'ge', value: 1000000 },
        {
          kind: 'group', combinator: 'or', items: [
            { kind: 'compare', field: 'priority', op: 'eq', value: 'high' },
            { kind: 'compare', field: 'priority', op: 'eq', value: 'normal' },
          ],
        },
      ],
    };
    const expr = renderCondition(g);
    expect(expr).toBe("total_amount >= 1000000 and (priority == 'high' or priority == 'normal')");
    expect(renderCondition(parseCondition(expr).structure!)).toBe(expr);
  });

  it('رشته با کوتیشن و بک‌اسلش', () => {
    const g: CondGroup = { combinator: 'and', items: [{ kind: 'compare', field: 'note', op: 'eq', value: "it's ok" }] };
    const expr = renderCondition(g);
    expect(parseCondition(expr).structure!.items[0]).toMatchObject({ value: "it's ok" });
  });

  it('شرط خالی → True', () => {
    expect(renderCondition({ combinator: 'and', items: [] })).toBe('True');
  });

  it('فیلد خالی خطا می‌دهد', () => {
    expect(() => renderCondition({ combinator: 'and', items: [{ kind: 'compare', field: '', op: 'eq', value: 1 }] })).toThrow(CondParseError);
  });
});

describe('ابزارها', () => {
  it('coerceValue: عدد/بولی/رشته', () => {
    expect(coerceValue('42')).toBe(42);
    expect(coerceValue('-3.5')).toBe(-3.5);
    expect(coerceValue('true')).toBe(true);
    expect(coerceValue('false')).toBe(false);
    expect(coerceValue('تهران')).toBe('تهران');
    expect(coerceValue('')).toBe('');
  });

  it('emptyCondition یک ردیف آماده می‌سازد', () => {
    const g = emptyCondition();
    expect(g.items).toHaveLength(1);
    expect((g.items[0] as any).kind).toBe('compare');
  });
});
