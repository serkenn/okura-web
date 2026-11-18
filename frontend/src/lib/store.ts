// 画面の共有の状態（ログインした人・世帯・語彙・最新の結果・件数）。React からは useS で読む
import { useSyncExternalStore } from 'react';
import { get } from './api';

export type Person = { person_id: string; display_name: string; birth_on?: string | null; is_me?: boolean; [k: string]: any };

export type Store = {
  me: any;
  household: any;
  persons: Person[];
  meta: any;
  latest: any;
  proposals: number;
  evidenceNew: number;
  bookPending: number;
  records: any[] | null;
};

export const S: Store = { me: null, household: null, persons: [], meta: null, latest: null, proposals: 0, evidenceNew: 0, bookPending: 0, records: null };

let version = 0;
const subs = new Set<() => void>();
const subscribe = (fn: () => void) => { subs.add(fn); return () => { subs.delete(fn); }; };

export function setS(patch: Partial<Store>) {
  Object.assign(S, patch);
  version += 1;
  for (const fn of [...subs]) fn();
}

/** 共有の状態を読む（変わったら描き直す）。例：const persons = useS((s) => s.persons) */
export function useS<T>(sel: (s: Store) => T): T {
  useSyncExternalStore(subscribe, () => version);
  return sel(S);
}

export async function loadMe() { setS({ me: await get('/api/me') }); return S.me; }

export async function loadHousehold(fresh = false) {
  const r = await get('/api/household', { fresh });
  setS({ household: r, persons: r.persons });
  return r;
}

// 記録の種類の名前から、英字（内部の名前）を含むかっこの注記を外す（例：「医療費の支払（on は支払った日）」→「医療費の支払」）
function cleanTitle(t: unknown) { return String(t || '').replace(/[（(][^）)]*[A-Za-z_][^）)]*[）)]/g, '').trim(); }

let metaPending: Promise<any> | null = null;
export function loadMeta(): Promise<any> {
  if (S.meta) return Promise.resolve(S.meta);
  metaPending ??= get('/api/meta').then((m0) => {
    const fix = (k: any) => ({ ...k, title: cleanTitle(k.title) || '記録' });
    const m = { ...m0, records: (m0.records || []).map(fix), ledger: (m0.ledger || []).map(fix) };
    setS({ meta: m });
    return m;
  }).finally(() => { metaPending = null; });
  return metaPending;
}

// 最新の結果。同じ結果を持っていれば、まとめ（数百 KB）は送ってもらわない
export async function loadLatest() {
  const prev = S.latest && S.latest.result && S.latest.result.digest ? S.latest.result : null;
  const q = prev ? `?have=${encodeURIComponent(prev.hash)}&cv=${encodeURIComponent(prev.cv || '')}` : '';
  const r = await get(`/api/results/latest${q}`);
  if (r.result && r.result.unchanged && prev) r.result.digest = prev.digest;
  // 中身が同じなら描き直さない（15秒ごとの確認で画面を揺らさない）
  const light = (x: any) => JSON.stringify({ ...x, result: x.result && { ...x.result, digest: null } });
  const same = !!S.latest && S.latest.result?.digest === r.result?.digest && light(S.latest) === light(r);
  if (!same) setS({ latest: r });
  return S.latest;
}

export async function loadRecords(force = false) {
  if (!S.records || force) setS({ records: (await get('/api/records', { fresh: force })).records });
  return S.records as any[];
}

export function personName(pid: string | null | undefined) {
  if (!pid) return '';
  const p = S.persons.find((x) => x.person_id === pid);
  return p ? p.display_name : '非公開の人';
}

export function kindMeta(kind: string) {
  if (!S.meta) return null;
  return S.meta.records.find((k: any) => k.kind === kind) || S.meta.ledger.find((k: any) => k.kind === kind) || null;
}

export function kindTitle(kind: string) {
  const k = kindMeta(kind);
  return k ? k.title : '記録';
}

export function formCtx() {
  return { persons: S.persons, records: S.records || [], kindTitle, enumExtra: S.meta ? S.meta.expense_categories : {} };
}

/** 最新の結果のまとめ（なければ null）。React の中では useDigest() を使う */
export function digest() { return S.latest && S.latest.result ? S.latest.result.digest : null; }
export function useDigest() { return useS((s) => (s.latest && s.latest.result ? s.latest.result.digest : null)); }
