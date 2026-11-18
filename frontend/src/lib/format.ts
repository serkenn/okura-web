// 表示の書式（判定コアの値を丸めずに、そのまま言葉にする）
export const yen = (n: unknown) => (n === null || n === undefined || n === '') ? '' : `${Number(n).toLocaleString('ja-JP')}円`;

export function fmtValue(v: any): string | null {
  if (!v) return null;
  switch (v.type) {
    case 'yen': return yen(v.amount);
    case 'yen_range': return `${yen(v.min)}〜${yen(v.max)}`;
    case 'bool': return v.value ? 'はい' : 'いいえ';
    case 'integer': return String(v.value);
    case 'category': return String(v.value);
    case 'date': return v.on;
    default: return v.value !== undefined && typeof v.value !== 'object' ? String(v.value) : '—';
  }
}

export function wareki(y: number) { return y >= 2019 ? `令和${y - 2018}年` : `${y}年`; }

export function timeLabel(t: any) {
  if (!t) return '';
  if (t.tax_year) return `${wareki(t.tax_year)}分`;
  if (t.fiscal_year) return `${wareki(t.fiscal_year)}度`;
  if (t.on) return `判定日 ${t.on}`;
  return '';
}

export function timeKey(t: any) {
  if (t.tax_year) return `Y${t.tax_year}`;
  if (t.fiscal_year) return `FY${t.fiscal_year}`;
  if (t.on) return `D${t.on}`;
  return JSON.stringify(t);
}

export function ageOn(birth: string | null | undefined, on: string) {
  if (!birth) return null;
  const b = new Date(birth), d = new Date(on);
  let a = d.getFullYear() - b.getFullYear();
  if (d.getMonth() < b.getMonth() || (d.getMonth() === b.getMonth() && d.getDate() < b.getDate())) a--;
  return a;
}

export function today() {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function initials(name: string | null | undefined) { return (name || '?').trim().slice(0, 1); }
