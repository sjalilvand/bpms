// فاز ۴ — شرط‌ساز بصری: تجزیه و رندر عبارت شرط مسیر (آینه منطق بک‌اند)
// عبارت تولیدی پایتونی است؛ موتور SpiffWorkflow آن را با معنای پایتونی ارزیابی می‌کند.

export type CondOp =
  | 'eq' | 'ne' | 'gt' | 'ge' | 'lt' | 'le'
  | 'in' | 'not_in' | 'contains' | 'empty' | 'not_empty';

export interface CondCompare {
  kind: 'compare';
  field: string;
  op: CondOp;
  value?: unknown;
  negate?: boolean;
}

export interface CondGroup {
  kind?: 'group';
  combinator: 'and' | 'or';
  items: (CondCompare | CondGroup)[];
}

export interface CondParseResult {
  structure: CondGroup | null;
  error: string | null;
}

export const OP_LABELS: Record<CondOp, string> = {
  eq: 'برابر است با',
  ne: 'برابر نیست با',
  gt: 'بزرگ‌تر از',
  ge: 'بزرگ‌تر یا مساوی',
  lt: 'کوچک‌تر از',
  le: 'کوچک‌تر یا مساوی',
  in: 'در فهرست است',
  not_in: 'در فهرست نیست',
  contains: 'شامل مقدار است',
  empty: 'خالی است',
  not_empty: 'خالی نیست',
};

export const OP_SYMBOL: Record<string, string> = {
  eq: '==', ne: '!=', gt: '>', ge: '>=', lt: '<', le: '<=',
  in: 'in', not_in: 'not in', contains: 'in', empty: 'is None', not_empty: 'is not None',
};

export const OPS_WITH_VALUE: CondOp[] = ['eq', 'ne', 'gt', 'ge', 'lt', 'le', 'in', 'not_in', 'contains'];

export class CondParseError extends Error {}

// ---------------- توکنایزر ----------------
type Tok = { t: 'str'; v: string } | { t: 'num'; v: number } | { t: 'id'; v: string } | { t: 'op'; v: string };

const OPS = ['==', '!=', '>=', '<=', '&&', '||', '>', '<', '(', ')', '[', ']', ',', '.'];

function tokenize(src: string): Tok[] {
  const toks: Tok[] = [];
  let i = 0;
  while (i < src.length) {
    const ch = src[i];
    if (/\s/.test(ch)) { i++; continue; }
    if (ch === "'" || ch === '"') {
      let j = i + 1, out = '';
      while (j < src.length && src[j] !== ch) {
        if (src[j] === '\\' && j + 1 < src.length) { out += src[j + 1]; j += 2; continue; }
        out += src[j]; j++;
      }
      if (j >= src.length) throw new CondParseError('رشته بسته نشده است');
      toks.push({ t: 'str', v: out });
      i = j + 1;
      continue;
    }
    if (/[0-9]/.test(ch) || (ch === '.' && /[0-9]/.test(src[i + 1] || ''))) {
      let j = i, num = '';
      while (j < src.length && /[0-9.]/.test(src[j])) { num += src[j]; j++; }
      toks.push({ t: 'num', v: Number(num) });
      i = j;
      continue;
    }
    if (/[A-Za-z_\u0600-\u06FF]/.test(ch)) {
      let j = i, id = '';
      while (j < src.length && /[A-Za-z0-9_\u0600-\u06FF]/.test(src[j])) { id += src[j]; j++; }
      toks.push({ t: 'id', v: id });
      i = j;
      continue;
    }
    const two = src.slice(i, i + 2);
    if (OPS.includes(two)) { toks.push({ t: 'op', v: two }); i += 2; continue; }
    if (OPS.includes(ch)) { toks.push({ t: 'op', v: ch }); i += 1; continue; }
    throw new CondParseError(`نویسه نامعتبر: «${ch}»`);
  }
  return toks;
}

const isKw = (tok: Tok | undefined, kw: string) => !!tok && tok.t === 'id' && tok.v.toLowerCase() === kw;
const isOp = (tok: Tok | undefined, op: string) => !!tok && tok.t === 'op' && tok.v === op;

// ---------------- پارسر بازگشتی-نزولی (مطابق زیرمجموعه مجاز بک‌اند) ----------------
class TsParser {
  private toks: Tok[];
  private i = 0;
  constructor(src: string) {
    this.toks = tokenize(src);
  }
  private peek(): Tok | undefined { return this.toks[this.i]; }
  private next(): Tok | undefined { return this.toks[this.i++]; }

  parseTop(): CondGroup {
    const g = this.parseAnd();
    if (this.i < this.toks.length) throw new CondParseError('عبارت کامل تجزیه نشد');
    if ((g as CondGroup).items) return g as CondGroup;
    return { combinator: 'and', items: [g] };
  }

  private parseAnd(): CondCompare | CondGroup {
    const items: (CondCompare | CondGroup)[] = [this.parseOrSingle()];
    while (isKw(this.peek(), 'and') || isOp(this.peek(), '&&')) {
      this.next();
      items.push(this.parseOrSingle());
    }
    if (items.length === 1) return items[0];
    return { combinator: 'and', items };
  }

  private parseOrSingle(): CondCompare | CondGroup {
    const first = this.parseNot();
    if (!(isKw(this.peek(), 'or') || isOp(this.peek(), '||'))) return first;
    const items: (CondCompare | CondGroup)[] = [first];
    while (isKw(this.peek(), 'or') || isOp(this.peek(), '||')) {
      this.next();
      items.push(this.parseNot());
    }
    return { kind: 'group', combinator: 'or', items };
  }

  private parseNot(): CondCompare | CondGroup {
    if (isKw(this.peek(), 'not')) {
      this.next();
      const inner = this.parseNot();
      if ((inner as CondGroup).items) throw new CondParseError('نفی گروه پشتیبانی نمی‌شود؛ در حالت دستی نگه دارید');
      const cmp = inner as CondCompare;
      return { ...cmp, negate: !cmp.negate };
    }
    return this.parseCompare();
  }

  private parseOperand(): string | string[] | number | boolean | null {
    const tok = this.next();
    if (!tok) throw new CondParseError('عبارت ناتمام است');
    if (tok.t === 'str') return tok.v;
    if (tok.t === 'num') return tok.v;
    if (tok.t === 'id') {
      const low = tok.v.toLowerCase();
      if (low === 'true') return true;
      if (low === 'false') return false;
      if (low === 'none') return null;
      // نام نقطه‌دار: order.total
      let name = tok.v;
      while (isOp(this.peek(), '.')) {
        this.next();
        const nxt = this.next();
        if (!nxt || nxt.t !== 'id') throw new CondParseError('مسیر نقطه‌دار ناقص است');
        name += '.' + nxt.v;
      }
      return name;
    }
    throw new CondParseError('عملوند نامعتبر');
  }

  private parseList(): unknown[] {
    if (!isOp(this.peek(), '[')) throw new CondParseError('انتظار فهرست [..]');
    this.next();
    const out: unknown[] = [];
    while (!isOp(this.peek(), ']')) {
      const v = this.parseOperand();
      out.push(v);
      if (isOp(this.peek(), ',')) { this.next(); continue; }
      break;
    }
    if (!isOp(this.peek(), ']')) throw new CondParseError('فهرست بسته نشده است');
    this.next();
    return out;
  }

  private parseCompare(): CondCompare | CondGroup {
    if (isOp(this.peek(), '(')) {
      this.next();
      const inner = this.parseAnd();
      if (!isOp(this.peek(), ')')) throw new CondParseError('پرانتز بسته نشده است');
      this.next();
      return inner;
    }
    const leftTok = this.peek();
    const leftIsLiteral = !!leftTok &&
      (leftTok.t === 'str' || (leftTok.t === 'id' && ['true', 'false', 'none'].includes(leftTok.v.toLowerCase())));
    const left = this.parseOperand();
    const isName = (v: unknown): v is string => typeof v === 'string';

    const tok = this.peek();
    if (tok && tok.t === 'op' && ['==', '!=', '>', '>=', '<', '<='].includes(tok.v)) {
      this.next();
      const sym = tok.v;
      const right = this.parseOperand();
      if (leftIsLiteral || !isName(left)) throw new CondParseError('سمت چپ شرط باید نام فیلد باشد');
      if (right === null && sym === '==') return { kind: 'compare', field: left, op: 'empty' };
      if (right === null && sym === '!=') return { kind: 'compare', field: left, op: 'not_empty' };
      const opMap: Record<string, CondOp> = { '==': 'eq', '!=': 'ne', '>': 'gt', '>=': 'ge', '<': 'lt', '<=': 'le' };
      return { kind: 'compare', field: left, op: opMap[sym], value: right };
    }
    if (isKw(tok, 'is')) {
      this.next();
      let negate = false;
      if (isKw(this.peek(), 'not')) { this.next(); negate = true; }
      if (isKw(this.peek(), 'none')) this.next();
      else throw new CondParseError('پس از is باید None بیاید');
      if (leftIsLiteral || !isName(left)) throw new CondParseError('سمت چپ شرط باید نام فیلد باشد');
      return { kind: 'compare', field: left, op: negate ? 'not_empty' : 'empty' };
    }
    if (isKw(tok, 'in') || (isKw(tok, 'not') && isKw(this.toks[this.i + 1], 'in'))) {
      let negate = false;
      if (isKw(tok, 'not')) { this.next(); negate = true; }
      this.next(); // in
      const right: unknown = isOp(this.peek(), '[') ? this.parseList() : this.parseOperand();
      if (isName(left) && !leftIsLiteral && Array.isArray(right)) {
        // field in [..]
        return negate
          ? { kind: 'compare', field: left, op: 'not_in', value: right }
          : { kind: 'compare', field: left, op: 'in', value: right };
      }
      if (leftIsLiteral && isName(right)) {
        // 'value' in field → contains
        return { kind: 'compare', field: right, op: 'contains', value: left, negate };
      }
      throw new CondParseError('الگوی in نامعتبر است (field in [..] یا value in field)');
    }
    throw new CondParseError('عملگر مقایسه شناخته‌شده نیست');
  }
}

/** عبارت پایتونی را به ساختار بصری تجزیه می‌کند؛ در حالت پشتیبانی‌نشده خطا می‌دهد (حالت دستی). */
export function parseCondition(expr: string): CondParseResult {
  if (!expr || !expr.trim()) return { structure: null, error: null };
  try {
    return { structure: new TsParser(expr).parseTop(), error: null };
  } catch (e) {
    return { structure: null, error: e instanceof CondParseError ? e.message : 'عبارت در شرط‌ساز بصری پشتیبانی نمی‌شود' };
  }
}

// ---------------- رندر ----------------
function fmtValue(v: unknown): string {
  if (v === null || v === undefined) return 'None';
  if (typeof v === 'boolean') return v ? 'True' : 'False';
  if (typeof v === 'number') return String(v);
  return "'" + String(v).replace(/\\/g, '\\\\').replace(/'/g, "\\'") + "'";
}

export function renderCompare(c: CondCompare): string {
  if (!c.field || !c.field.trim()) throw new CondParseError('نام فیلد خالی است');
  let body: string;
  switch (c.op) {
    case 'empty': body = `${c.field} is None`; break;
    case 'not_empty': body = `${c.field} is not None`; break;
    case 'contains': body = `${fmtValue(c.value)} in ${c.field}`; break;
    case 'in':
    case 'not_in': {
      const list = Array.isArray(c.value) ? c.value : [];
      if (!list.length) throw new CondParseError('عملگر in به فهرست مقادیر غیرخالی نیاز دارد');
      body = `${c.field} ${c.op === 'in' ? 'in' : 'not in'} [${list.map(fmtValue).join(', ')}]`;
      break;
    }
    default: body = `${c.field} ${OP_SYMBOL[c.op]} ${fmtValue(c.value)}`;
  }
  return c.negate ? `not (${body})` : body;
}

export function renderCondition(g: CondGroup): string {
  const parts: string[] = [];
  for (const it of g.items || []) {
    if ((it as CondGroup).items) {
      const sub = renderCondition(it as CondGroup);
      parts.push(`(${sub})`);
    } else {
      parts.push(renderCompare(it as CondCompare));
    }
  }
  if (!parts.length) return 'True';
  return parts.join(` ${g.combinator} `);
}

/** ساخت شرط خالی با یک ردیف */
export function emptyCondition(): CondGroup {
  return { combinator: 'and', items: [{ kind: 'compare', field: '', op: 'eq', value: '' }] };
}

/** تبدیل مقدار تایپ‌شده رابط کاربری به مقدار ساختاری (عدد/بولی/رشته) */
export function coerceValue(raw: string): string | number | boolean | null {
  const t = raw.trim();
  if (t === '') return '';
  if (/^-?\d+(\.\d+)?$/.test(t)) return Number(t);
  const low = t.toLowerCase();
  if (low === 'true') return true;
  if (low === 'false') return false;
  if (low === 'none' || low === 'null') return null;
  return t;
}

/** آیا این جریان از دروازه شرطی خارج می‌شود؟ (برای نمایش شرط‌ساز) */
export const GATEWAY_TYPES = ['bpmn:ExclusiveGateway', 'bpmn:InclusiveGateway'];

export function isGatewayFlow(sourceType: string | undefined): boolean {
  return !!sourceType && GATEWAY_TYPES.includes(sourceType);
}
