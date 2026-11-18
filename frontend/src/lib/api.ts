// サーバーとのやり取り（同じオリジンだけ。CSRF のトークンをヘッダーで送る）
let csrf: string | null = null;

export function setCsrf(v: string | null) { csrf = v; }

export class ApiError extends Error {
  status: number;
  code?: string;
  detail?: any;
  constructor(status: number, body: any) {
    const e = (body && body.error) || {};
    super(e.message || `エラー（${status}）`);
    this.status = status;
    this.code = e.code;
    this.detail = e.detail;
  }
}

// 読み取りの短い記憶（このタブのメモリーだけ。保存しない）。
// スマホからは1往復が重いので、同じ画面に戻る・タブを切り替えるときは往復しない。
// 自分が書き込んだら（GET 以外）すべて捨てる。ほかの家族の変更は、長くても FRESH_MS 遅れて見える。
const FRESH_MS = 30000;
const memo = new Map<string, { at: number; data: any }>();
const inflight = new Map<string, { gen: number; pr: Promise<any> }>(); // 同じ問い合わせを重ねない
let gen = 0; // 書き込みのたびに進める（書き込みの前に出た読み取りの答えは記憶しない）
const NO_MEMO = [/^\/api\/status/, /^\/api\/me\b/, /^\/api\/results\/latest/, /^\/api\/agent\//, /^\/api\/guest\//, /^\/api\/join/];

// 記憶を捨てたことを、読んでいる画面（useApi）に知らせる
const invalidated = new Set<() => void>();
export function onInvalidate(fn: () => void): () => void { invalidated.add(fn); return () => { invalidated.delete(fn); }; }

/** 記憶を捨てる。notify: 読んでいる画面に取り直させる */
export function forgetCache(notify = true) {
  memo.clear();
  gen += 1;
  if (notify) for (const fn of [...invalidated]) fn();
}

export type ApiOpts = { raw?: BodyInit; contentType?: string; keepCache?: boolean };

export async function api<T = any>(method: string, path: string, body?: unknown, opts: ApiOpts = {}): Promise<T> {
  const headers: Record<string, string> = {};
  let data: BodyInit | undefined;
  if (opts.raw !== undefined) {
    data = opts.raw;
    headers['Content-Type'] = opts.contentType || 'application/octet-stream';
  } else if (body !== undefined) {
    data = JSON.stringify(body);
    headers['Content-Type'] = 'application/json';
  }
  if (method !== 'GET' && csrf) headers['X-CSRF-Token'] = csrf;
  const writes = method !== 'GET' && !opts.keepCache;
  if (writes) forgetCache(false);
  let res: Response;
  try { res = await fetch(path, { method, headers, body: data, credentials: 'same-origin' }); } finally { if (writes) forgetCache(true); }
  let out: any = null;
  const text = await res.text();
  try { out = text ? JSON.parse(text) : null; } catch { out = null; }
  if (!res.ok || (out && out.ok === false)) throw new ApiError(res.status, out);
  return out as T;
}

function cacheable(p: string) { return !NO_MEMO.some((re) => re.test(p)); }

/** 記憶にあれば、その値（古くてもよい）。なければ undefined */
export function peek<T = any>(p: string): { data: T; fresh: boolean } | undefined {
  const hit = memo.get(p);
  return hit ? { data: hit.data as T, fresh: Date.now() - hit.at < FRESH_MS } : undefined;
}

/** fresh: true なら記憶を使わずに取り直す（取り直した値は記憶する） */
export function get<T = any>(p: string, { fresh = false }: { fresh?: boolean } = {}): Promise<T> {
  const can = cacheable(p);
  if (can && !fresh) {
    const hit = memo.get(p);
    if (hit && Date.now() - hit.at < FRESH_MS) return Promise.resolve(hit.data as T);
  }
  const cur = inflight.get(p);
  if (cur && cur.gen === gen) return cur.pr;
  const at = Date.now();
  const g = gen;
  const pr: Promise<any> = api('GET', p).then((d) => {
    if (can && g === gen) memo.set(p, { at, data: d });
    return d;
  }).finally(() => { if (inflight.get(p)?.pr === pr) inflight.delete(p); });
  inflight.set(p, { gen: g, pr });
  return pr;
}

/** 先に取っておく（失敗しても黙る。表示はしない） */
export function prefetch(paths: string[]) {
  for (const p of paths) {
    const hit = memo.get(p);
    if (!hit || Date.now() - hit.at > FRESH_MS / 2) get(p).catch(() => {});
  }
}

export const post = <T = any>(p: string, b?: unknown, opts?: ApiOpts) => api<T>('POST', p, b === undefined ? {} : b, opts);
