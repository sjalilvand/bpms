// فرمول‌ساز امن — قرینه سمت مرورگر از app/modules/forms/safeeval.py
// بدون eval/Function — Parser بازگشتی-نزولی مشترک با بک‌اند
export type Resolver = (key: string) => unknown;

export class FormulaError extends Error {}

type Token = { kind: 'num' | 'str' | 'op' | 'ident'; value: string };

const TOKEN_RE = /\s*(?:(\d+\.\d+|\d+)|('[^']*'|"[^"]*")|(<=|>=|==|!=|&&|\|\||[+\-*/%()<>!,.])|([A-Za-z_\u0600-\u06FF][A-Za-z0-9_\u0600-\u06FF]*))/y;

function tokenize(expr: string): Token[] {
  const tokens: Token[] = [];
  let pos = 0;
  while (pos < expr.length) {
    TOKEN_RE.lastIndex = pos;
    const m = TOKEN_RE.exec(expr);
    if (!m) {
      if (expr.slice(pos).trim() === '') break;
      throw new FormulaError(`نویسه نامعتبر: ${expr.slice(pos, pos + 5)}`);
    }
    pos = m[0].length + (m[0].length - (m[0].trimStart() || '').length) === 0 ? m.index + m[0].length : TOKEN_RE.lastIndex;
    if (m[1] !== undefined) tokens.push({ kind: 'num', value: m[1] });
    else if (m[2] !== undefined) tokens.push({ kind: 'str', value: m[2] });
    else if (m[3] !== undefined) tokens.push({ kind: 'op', value: m[3] });
    else if (m[4] !== undefined) tokens.push({ kind: 'ident', value: m[4] });
  }
  return tokens;
}

function toNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0;
  if (typeof v === 'boolean') return v ? 1 : 0;
  if (typeof v === 'number') return v;
  const s = String(v).trim().replace(/,/g, '');
  const n = s.includes('.') ? parseFloat(s) : parseInt(s, 10);
  if (isNaN(n)) throw new FormulaError(`«${v}» عدد نیست`);
  return n;
}

class Parser {
  private i = 0;
  constructor(private toks: Token[], private resolver: Resolver) {}

  peek(): Token | null {
    return this.i < this.toks.length ? this.toks[this.i] : null;
  }
  next(): Token | null {
    return this.i < this.toks.length ? this.toks[this.i++] : null;
  }
  expect(v: string): void {
    const t = this.next();
    if (!t || t.value !== v) throw new FormulaError(`انتظار «${v}»`);
  }

  parseOr(): unknown {
    let left = this.parseAnd();
    while (this.peek()?.value === '||' || (this.peek()?.kind === 'ident' && this.peek()?.value === 'or')) {
      this.next();
      const right = this.parseAnd();
      left = Boolean(left) || Boolean(right);
    }
    return left;
  }
  parseAnd(): unknown {
    let left = this.parseNot();
    while (this.peek()?.value === '&&' || (this.peek()?.kind === 'ident' && this.peek()?.value === 'and')) {
      this.next();
      const right = this.parseNot();
      left = Boolean(left) && Boolean(right);
    }
    return left;
  }
  parseNot(): unknown {
    const t = this.peek();
    if (t && (t.value === '!' || (t.kind === 'ident' && t.value === 'not'))) {
      this.next();
      return !this.parseNot();
    }
    return this.parseCmp();
  }
  parseCmp(): unknown {
    const left = this.parseAdd();
    const op = this.peek()?.value;
    if (op && ['<', '>', '<=', '>=', '==', '!='].includes(op)) {
      this.next();
      const right = this.parseAdd();
      switch (op) {
        case '<': return (left as number) < (right as number);
        case '>': return (left as number) > (right as number);
        case '<=': return (left as number) <= (right as number);
        case '>=': return (left as number) >= (right as number);
        case '==': return left === right;
        default: return left !== right;
      }
    }
    return left;
  }
  parseAdd(): unknown {
    let left = this.parseMul();
    while (this.peek()?.value === '+' || this.peek()?.value === '-') {
      const op = this.next()!.value;
      const right = this.parseMul();
      if (op === '+') {
        if (typeof left === 'string' && typeof right === 'string') left = left + right;
        else left = toNum(left) + toNum(right);
      } else left = toNum(left) - toNum(right);
    }
    return left;
  }
  parseMul(): unknown {
    let left = this.parseUnary();
    while (['*', '/', '%'].includes(this.peek()?.value as string)) {
      const op = this.next()!.value;
      const right = this.parseUnary();
      if (op === '*') left = toNum(left) * toNum(right);
      else if (op === '/') {
        const d = toNum(right);
        if (d === 0) throw new FormulaError('تقسیم بر صفر');
        left = toNum(left) / d;
      } else {
        const d = toNum(right);
        if (d === 0) throw new FormulaError('باقیمانده بر صفر');
        left = toNum(left) % d;
      }
    }
    return left;
  }
  parseUnary(): unknown {
    const t = this.peek();
    if (t?.value === '-') { this.next(); return -toNum(this.parseUnary()); }
    if (t?.value === '+') { this.next(); return toNum(this.parseUnary()); }
    return this.parsePrimary();
  }
  parsePrimary(): unknown {
    const t = this.next();
    if (!t) throw new FormulaError('عبارت ناقص است');
    if (t.kind === 'num') return t.value.includes('.') ? parseFloat(t.value) : parseInt(t.value, 10);
    if (t.kind === 'str') return t.value.slice(1, -1);
    if (t.kind === 'ident') {
      const low = t.value.toLowerCase();
      if (low === 'true') return true;
      if (low === 'false') return false;
      const up = t.value.toUpperCase();
      if (['SUM', 'MIN', 'MAX', 'COUNT', 'ROUND', 'ABS', 'IF'].includes(up)) return this.parseCall(up);
      return this.resolver(t.value);
    }
    if (t.value === '(') {
      const inner = this.parseOr();
      this.expect(')');
      return inner;
    }
    throw new FormulaError(`عبارت نامعتبر نزدیک «${t.value}»`);
  }
  parseCall(fn: string): unknown {
    this.expect('(');
    if (['SUM', 'MIN', 'MAX', 'COUNT'].includes(fn)) {
      const path = this.parsePath();
      this.expect(')');
      return this.aggregate(fn, path);
    }
    const args: unknown[] = [];
    if (this.peek()?.value !== ')') {
      args.push(this.parseOr());
      while (this.peek()?.value === ',') { this.next(); args.push(this.parseOr()); }
    }
    this.expect(')');
    return this.call(fn, args);
  }
  parsePath(): string {
    const t = this.next();
    if (!t || t.kind !== 'ident') throw new FormulaError('نام فیلد آرایه‌ای لازم است');
    let path = t.value;
    while (this.peek()?.value === '.') {
      this.next();
      const t2 = this.next();
      if (!t2 || t2.kind !== 'ident') throw new FormulaError('مسیر فیلد نامعتبر است');
      path += '.' + t2.value;
    }
    return path;
  }
  aggregate(fn: string, path: string): unknown {
    const parts = path.split('.');
    const rows = this.resolver(`__list__${parts[0]}`) as unknown[] | null;
    let values: unknown[];
    if (!rows) values = [];
    else if (parts.length === 1) values = rows.filter((v) => v !== null && v !== undefined && v !== '');
    else values = rows.map((row) => (row && typeof row === 'object' ? (row as Record<string, unknown>)[parts[parts.length - 1]] : null));
    const nums = values.filter((v) => v !== null && v !== undefined && v !== '').map(toNum);
    if (fn === 'COUNT') return parts.length === 1 ? values.length : nums.length;
    if (fn === 'SUM') return nums.reduce((a, b) => a + b, 0);
    if (!nums.length) return 0;
    return fn === 'MIN' ? Math.min(...nums) : Math.max(...nums);
  }
  call(fn: string, args: unknown[]): unknown {
    if (fn === 'ROUND') return args.length === 1 ? Math.round(toNum(args[0])) : Number(toNum(args[0]).toFixed(parseInt(String(args[1]), 10)));
    if (fn === 'ABS') return Math.abs(toNum(args[0]));
    if (fn === 'IF') return args[0] ? args[1] : args[2];
    throw new FormulaError(`تابع «${fn}» مجاز نیست`);
  }
}

export function evaluateFormula(expr: string | null | undefined, resolver: Resolver, fallback: unknown = null): unknown {
  if (!expr || !expr.trim()) return fallback;
  try {
    const p = new Parser(tokenize(expr), resolver);
    const result = p.parseOr();
    if (p.peek() !== null) throw new FormulaError('عبارت کامل تجزیه نشد');
    return result;
  } catch (e) {
    if (e instanceof FormulaError) return fallback;
    return fallback;
  }
}

export function evaluateCondition(expr: string | null | undefined, resolver: Resolver): boolean {
  return Boolean(evaluateFormula(expr, resolver, false));
}
