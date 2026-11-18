// 家計簿（月の収支）・入出金（登録待ちを含む）・口座・カテゴリ。呼び名と型は docs/household-ui-references.md
import { Fragment, createContext, useContext, useEffect, useRef, useState, useSyncExternalStore, type ButtonHTMLAttributes, type CSSProperties, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Link, useNavigate, useParams } from 'react-router';
import { get, post, prefetch, forgetCache } from '../lib/api';
import { today } from '../lib/format';
import { refreshStatus, warmers } from '../lib/status';
import { S, useS, personName, loadMeta, kindMeta } from '../lib/store';
import { useApi } from '../lib/useApi';
import { Icon } from '../ui/Icon';
import { Avatar, ErrorNote, Skeleton } from '../ui/bits';
import { Sheet, askText, confirmBox, errorToast, modal, openOverlay, openSheet, toast } from '../ui/overlay';
import { openRecordForm } from './Data';

type Bk = { accounts: any[]; categories: any[] };
type After = () => void;

const COLORS = ['#e8590c', '#2f9e44', '#1971c2', '#ae3ec9', '#f08c00', '#0c8599', '#d6336c', '#5f3dc4', '#66a80f', '#c2255c', '#1098ad', '#e67700', '#495057', '#7048e8', '#37b24d', '#868e96', '#adb5bd'];
const KIND_LABEL: Record<string, string> = { bank: '銀行', card: 'カード', emoney: '電子マネー', securities: '証券', cash: '財布', other: 'その他' };
const KIND_ICON: Record<string, string> = { bank: 'building', card: 'card', emoney: 'phone', securities: 'chart', cash: 'wallet', other: 'dots' };
const MAX_BULK = 25;
const enc = encodeURIComponent;

// ------------------------------------------------------------------ 共通
const fmt = (n: any) => Number(n || 0).toLocaleString('ja-JP');
const signed = (n: number) => `${n < 0 ? '−' : ''}${fmt(Math.abs(n))}`;
/** 入力の文字から数字だけを読む（なければ NaN） */
const digits = (s: unknown) => parseInt(String(s).replace(/[^\d]/g, ''), 10);

function thisMonth() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; }
function month() { return sessionStorage.getItem('okura.book.month') || thisMonth(); }
function shiftMonth(m: string, d: number) { let [y, mo] = m.split('-').map(Number); mo += d; while (mo < 1) { mo += 12; y -= 1; } while (mo > 12) { mo -= 12; y += 1; } return `${y}-${String(mo).padStart(2, '0')}`; }
function monthLabel(m: string) { const [y, mo] = m.split('-'); return `${y}年${Number(mo)}月`; }
function owner() { return sessionStorage.getItem('okura.book.owner') || ''; }
function bookTab() { return sessionStorage.getItem('okura.book.tab') || 'flow'; }
const WD = ['日', '月', '火', '水', '木', '金', '土'];
function dayLabel(d: string) { const x = new Date(`${d}T00:00:00`); return `${x.getMonth() + 1}月${x.getDate()}日（${WD[x.getDay()]}）`; }

// 月・人・タブの選択（sessionStorage に置く。変えたら読んでいる画面を描き直す）
let pickVer = 0;
const pickSubs = new Set<() => void>();
const pickSubscribe = (fn: () => void) => { pickSubs.add(fn); return () => { pickSubs.delete(fn); }; };
function setPick(key: 'month' | 'owner' | 'tab', v: string) {
  sessionStorage.setItem(`okura.book.${key}`, v);
  pickVer += 1;
  for (const fn of [...pickSubs]) fn();
}
const setMonth = (m: string) => setPick('month', m);
function usePick() {
  useSyncExternalStore(pickSubscribe, () => pickVer);
  return { month: month(), owner: owner(), tab: bookTab() };
}

// 口座とカテゴリ（/api/book/accounts）。画面は WithBook で読み、シートには開いたときの値を渡す
const EMPTY: Bk = { accounts: [], categories: [] };
const BookCtx = createContext<Bk>(EMPTY);
const useBk = () => useContext(BookCtx);

function WithBook({ children }: { children: ReactNode }) {
  const q = useApi<Bk>('/api/book/accounts');
  if (!q.data) return q.error ? <ErrorNote error={q.error} /> : <Skeleton />;
  return <BookCtx.Provider value={q.data}>{children}</BookCtx.Provider>;
}

function bookSheet<T = any>(bk: Bk, render: (close: (v?: T | null) => void) => ReactNode) {
  return openSheet<T>((close) => <BookCtx.Provider value={bk}>{render(close)}</BookCtx.Provider>);
}

function cat(bk: Bk, acc: any) { return (bk.categories || []).find((c) => c.account === acc); }
function account(bk: Bk, acc: any) { return (bk.accounts || []).find((a) => a.account === acc); }
function topOf(bk: Bk, acc: any) { const c = cat(bk, acc); return c && c.parent ? cat(bk, c.parent) : c; }
function isUncat(acc: any) { return acc === 'Expenses:Uncategorized' || acc === 'Income:Uncategorized'; }
function catColor(bk: Bk, acc: any) {
  const top = topOf(bk, acc);
  if (!top || isUncat(top.account)) return '#adb5bd';
  const tops = bk.categories.filter((c) => !c.parent && c.kind === top.kind);
  return COLORS[Math.max(0, tops.findIndex((c) => c.account === top.account)) % COLORS.length];
}
function catName(bk: Bk, acc: any): string {
  const c = cat(bk, acc);
  if (!c) { const a = account(bk, acc); return a ? `振替 → ${a.label}` : '未分類'; }
  const p = c.parent ? cat(bk, c.parent) : null;
  return p ? `${p.label} › ${c.label}` : c.label;
}
function CatIcon({ acc, size = 18, view = null }: { acc: any; size?: number; view?: any }) {
  const bk = useBk();
  if (view && view.transfer_to) return <span className="cat-ico" style={{ background: '#868e96' }}><Icon name="arrows" size={size} /></span>;
  const c = cat(bk, acc);
  return <span className="cat-ico" style={{ background: catColor(bk, acc) }}><Icon name={(c && c.icon) || 'question'} size={size} /></span>;
}

// 画面の中の切り替え（タブ・月・人）：待つ間は今の表示を薄くして、押したことが分かるようにする
// （古い .content.busy と同じ見た目。枠の .content には触れないので、自分の包みに付ける）
const BUSY: CSSProperties = { opacity: 0.55, pointerEvents: 'none', transition: 'opacity .12s ease .08s' };
function useSwitching(q: { data: any; error: any; refreshing: boolean }, path: string) {
  const shown = useRef(path);
  if (!q.refreshing && (q.data !== undefined || q.error)) shown.current = path;
  // 取り直しに失敗したとき：前の表示のまま、知らせる
  const err = q.data !== undefined ? q.error : undefined;
  useEffect(() => { if (err) errorToast(err); }, [err]);
  return q.refreshing && shown.current !== path;
}

function MonthPicker({ m, close }: { m: string; close: () => void }) {
  const [y, setY] = useState(Number(m.slice(0, 4)));
  return (
    <Sheet title="月を選ぶ" onClose={close}>
      <div>
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: '10px' }}>
          <button type="button" className="btn ghost small" onClick={() => setY(y - 1)}><Icon name="chevronLeft" size={16} /></button><b>{`${y}年`}</b>
          <button type="button" className="btn ghost small" onClick={() => setY(y + 1)}><Icon name="chevronRight" size={16} /></button>
        </div>
        <div className="month-grid">{Array.from({ length: 12 }, (_, i) => {
          const v = `${y}-${String(i + 1).padStart(2, '0')}`;
          return <button type="button" key={v} className={`btn ${v === m ? 'primary' : ''}`} onClick={() => { close(); setMonth(v); }}>{`${i + 1}月`}</button>;
        })}</div>
      </div>
    </Sheet>
  );
}

function MonthBar() {
  const { month: m } = usePick();
  const pick = () => { openSheet((close) => <MonthPicker m={m} close={() => close()} />); };
  return (
    <div className="month-bar">
      <button type="button" className="btn ghost" aria-label="前の月" onClick={() => setMonth(shiftMonth(m, -1))}><Icon name="chevronLeft" size={18} /></button>
      <button type="button" className="mb-label" onClick={pick}>{monthLabel(m)}</button>
      <button type="button" className="btn ghost" aria-label="次の月" onClick={() => setMonth(shiftMonth(m, 1))}><Icon name="chevronRight" size={18} /></button>
    </div>
  );
}

function OwnerChips() {
  const persons = useS((s) => s.persons);
  const { owner: cur } = usePick();
  if (!persons || persons.length < 2) return null;
  return (
    <div className="chips-row">
      <button type="button" className={`pchip ${cur === '' ? 'on' : ''}`} onClick={() => setPick('owner', '')}><Icon name="users" size={14} />全員</button>
      {persons.map((p) => (
        <button type="button" key={p.person_id} className={`pchip ${cur === p.person_id ? 'on' : ''}`} onClick={() => setPick('owner', p.person_id)}>
          <Avatar id={p.person_id} name={p.display_name} small />{p.display_name}
        </button>
      ))}
    </div>
  );
}

// カテゴリを選ぶ：支出／収入／振替 → 大項目 → 中項目（「大項目」「中項目」の語は出さない）
type PickOpts = { kind?: string; current?: string | null; fromAccount?: string | null };

function CategoryPicker({ kind = 'expense', current = null, fromAccount = null, done }: PickOpts & { done: (v: string | null) => void }) {
  const bk = useBk();
  const [tab, setTab] = useState<string>(() => { const c = cat(bk, current); return current && account(bk, current) ? 'transfer' : (c ? c.kind : kind); });
  const [top, setTop] = useState<any>(null);
  const seg = (
    <div className="seg" style={{ marginBottom: '12px' }}>
      {[['expense', '支出'], ['income', '収入'], ['transfer', '振替']].map(([k, l]) => <button type="button" key={k} className={tab === k ? 'on' : ''} onClick={() => { setTab(k); setTop(null); }}>{l}</button>)}
    </div>
  );
  let body: ReactNode;
  if (tab === 'transfer') {
    const list = bk.accounts.filter((a) => a.can_edit && a.account !== fromAccount);
    body = (
      <>{seg}{list.length ? (
        <div className="pick-list">{list.map((a) => (
          <button type="button" key={a.account} className={`pick-row ${current === a.account ? 'on' : ''}`} onClick={() => done(a.account)}>
            <span className="cat-ico" style={{ background: '#868e96' }}><Icon name={KIND_ICON[a.kind] || 'wallet'} size={16} /></span>{a.label}
          </button>
        ))}</div>
      ) : <div className="empty">振替先の口座がありません</div>}</>
    );
  } else if (!top) {
    const tops = bk.categories.filter((c) => c.kind === tab && !c.parent && !c.hidden);
    body = (
      <>{seg}<div className="cat-grid">{tops.map((c) => {
        const kids = bk.categories.filter((x) => x.parent === c.account && !x.hidden);
        const on = current && (current === c.account || (cat(bk, current) || {}).parent === c.account);
        return (
          <button type="button" key={c.account} className={`cat-tile ${on ? 'on' : ''}`} onClick={() => { if (kids.length) setTop(c); else done(c.account); }}>
            <CatIcon acc={c.account} size={20} /><span>{c.label}</span>
          </button>
        );
      })}</div></>
    );
  } else {
    const kids = bk.categories.filter((x) => x.parent === top.account && !x.hidden);
    body = (
      <>
        <button type="button" className="btn ghost small" onClick={() => setTop(null)}><Icon name="chevronLeft" size={15} />{top.label}</button>
        <div className="pick-list">
          <button type="button" className={`pick-row ${current === top.account ? 'on' : ''}`} onClick={() => done(top.account)}><CatIcon acc={top.account} size={16} />{`${top.label}（全体）`}</button>
          {kids.map((c) => (
            <button type="button" key={c.account} className={`pick-row ${current === c.account ? 'on' : ''}`} onClick={() => done(c.account)}>
              <CatIcon acc={c.account} size={16} />{c.label}
              {c.hint ? <span className="chip hint" title="申告のときに見返す書類"><Icon name="file" size={12} />{c.hint}</span> : null}
            </button>
          ))}
        </div>
      </>
    );
  }
  return <Sheet title="カテゴリ" onClose={() => done(null)}><div>{body}</div></Sheet>;
}

function pickCategory(bk: Bk, opts: PickOpts = {}): Promise<string | null> {
  return bookSheet<string>(bk, (close) => <CategoryPicker {...opts} done={(v) => close(v)} />);
}

function CatButton({ value, onChange, opts }: { value: string | null; onChange: (v: string) => void; opts: () => PickOpts }) {
  const bk = useBk();
  return (
    <button type="button" className="cat-btn" onClick={async () => {
      const v = await pickCategory(bk, { ...opts(), current: value });
      if (v) onChange(v);
    }}>
      {value ? <CatIcon acc={value} size={16} view={account(bk, value) ? { transfer_to: value } : null} /> : <Icon name="question" size={16} />}
      <span>{value ? catName(bk, value) : '未分類'}</span><Icon name="chevronRight" size={15} cls="muted" />
    </button>
  );
}

function amountClass(v: any) { return v.transfer_to ? 'amt tr' : v.amount > 0 ? 'amt in' : 'amt'; }

// ------------------------------------------------------------------ 分割（1件を複数のカテゴリに）
// parts：[{category, amount（正の数）}]。合計が total（正の数）になるまで行を足す
type SplitRow = { k: number; category: string | null; amount: number; text: string };
let splitSeq = 0;
function splitRows(total: number, initial?: any[] | null): SplitRow[] {
  const src = initial && initial.length ? initial : [{ category: null, amount: total }, { category: null, amount: 0 }];
  return src.map((p) => ({ k: ++splitSeq, category: p.category || null, amount: p.amount || 0, text: p.amount ? fmt(p.amount) : '' }));
}
function readSplit(rows: SplitRow[], total: number) {
  const sum = rows.reduce((a, r) => a + (r.amount || 0), 0);
  if (rows.some((r) => !r.category || !r.amount)) throw new Error('どの行もカテゴリと金額を入れてください');
  if (sum !== total) throw new Error(`合計が ${fmt(total)}円 になるようにしてください`);
  return rows.map((r) => ({ category: r.category, amount: r.amount }));
}

function SplitEditor({ total, kind, rows, setRows }: { total: number; kind: string; rows: SplitRow[]; setRows: (fn: (rows: SplitRow[]) => SplitRow[]) => void }) {
  const sum = rows.reduce((a, r) => a + (r.amount || 0), 0);
  const patch = (k: number, p: Partial<SplitRow>) => setRows((rs) => rs.map((r) => (r.k === k ? { ...r, ...p } : r)));
  return (
    <div className="stack">
      {rows.map((r) => (
        <div className="split-row" key={r.k}>
          <CatButton value={r.category} onChange={(c) => patch(r.k, { category: c })} opts={() => ({ kind })} />
          <input className="in split-amt" inputMode="numeric" placeholder="0" value={r.text} onChange={(e) => patch(r.k, { text: e.target.value, amount: digits(e.target.value) || 0 })} />
          {rows.length > 2 ? <button type="button" className="btn ghost small" aria-label="行を消す" onClick={() => setRows((rs) => rs.filter((x) => x.k !== r.k))}><Icon name="x" size={14} /></button> : null}
        </div>
      ))}
      <button type="button" className="btn ghost small" onClick={() => setRows((rs) => [...rs, { k: ++splitSeq, category: null, amount: 0, text: '' }])}><Icon name="plus" size={14} />行を足す</button>
      <div className={`split-rest ${sum === total ? 'ok' : 'bad'}`}>{sum === total ? '合計が一致' : `残り ${signed(total - sum)}円`}</div>
    </div>
  );
}

// ------------------------------------------------------------------ 入力（＋）
const FREQ: Array<[string, string]> = [['', 'しない'], ['daily', '毎日'], ['weekly', '毎週'], ['monthly', '毎月'], ['monthend', '月末']];

function InputSheet({ close, after }: { close: () => void; after?: After }) {
  const bk = useBk();
  const writable = bk.accounts.filter((a) => a.can_edit);
  const [kind, setKind] = useState('expense');
  const [category, setCategory] = useState<string | null>(null);
  const [split, setSplit] = useState<{ total: number; rows: SplitRow[] } | null>(null);
  const [amount, setAmount] = useState('');
  const [acct, setAcct] = useState<string>(writable[0] ? writable[0].account : '');
  const [date, setDate] = useState(today());
  const [payee, setPayee] = useState('');
  const [memo, setMemo] = useState('');
  const [freq, setFreq] = useState('');
  const [remember, setRemember] = useState(false);
  const [saving, setSaving] = useState(false);
  const amountRef = useRef<HTMLInputElement>(null);
  useEffect(() => { const t = setTimeout(() => amountRef.current?.focus(), 50); return () => clearTimeout(t); }, []);

  const toggleSplit = () => {
    const n = digits(amount);
    if (split) setSplit(null);
    else if (!n) toast('先に金額を入れてください', 'bad');
    else setSplit({ total: n, rows: splitRows(n, category ? [{ category, amount: n }, { category: null, amount: 0 }] : null) });
  };
  const save = async () => {
    const n = digits(amount);
    if (!n) { toast('金額を入れてください', 'bad'); return; }
    let parts: any[] | null = null;
    try { parts = split ? readSplit(split.rows, split.total) : null; } catch (e: any) { toast(e.message, 'bad'); return; }
    if (!parts && !category) { toast('カテゴリを選んでください', 'bad'); return; }
    const transfer = !parts && !!account(bk, category);
    const sign = kind === 'income' ? 1 : -1;
    const base = { account: acct, amount: sign * n, payee, memo };
    if (freq && parts) { toast('分割と繰り返しは一緒に使えません', 'bad'); return; }
    setSaving(true);
    try {
      if (freq) {
        await post('/api/book/recurring', { ...base, [transfer ? 'transfer_to' : 'category']: category, freq, start_on: date });
      } else {
        await post('/api/book/transactions', { ...base, date, remember, ...(parts ? { parts } : { [transfer ? 'transfer_to' : 'category']: category }) });
      }
      close(); toast('保存しました'); after && after();
    } catch (e) { setSaving(false); errorToast(e); }
  };
  return (
    <Sheet title="入力" onClose={close} footer={<button type="button" className="btn primary big" disabled={saving} onClick={save}>保存</button>}>
      <div className="stack">
        <div className="seg seg-wide">
          {[['expense', '支出'], ['income', '収入'], ['transfer', '振替']].map(([k, l]) => (
            <button type="button" key={k} className={kind === k ? 'on' : ''} onClick={() => { setKind(k); setCategory(null); setSplit(null); }}>{l}</button>
          ))}
        </div>
        <div className="amount-row"><span>¥</span><input ref={amountRef} className="in amount-in" inputMode="numeric" placeholder="0" autoComplete="off" value={amount} onChange={(e) => setAmount(e.target.value)} /></div>
        <div>
          {split
            ? <SplitEditor total={split.total} kind={kind} rows={split.rows} setRows={(fn) => setSplit((s) => (s ? { ...s, rows: fn(s.rows) } : s))} />
            : <CatButton value={category} onChange={setCategory} opts={() => ({ kind, fromAccount: acct })} />}
        </div>
        <div><button type="button" className="btn ghost small" hidden={kind === 'transfer'} onClick={toggleSplit}><Icon name="layers" size={14} />{split ? '分割をやめる' : '分割'}</button></div>
        <div className="grid c2">
          <label className="field"><span>口座</span>
            <select className="in" value={acct} onChange={(e) => setAcct(e.target.value)}>{writable.map((a) => <option key={a.account} value={a.account}>{a.label}</option>)}</select></label>
          <label className="field"><span>日付</span><input className="in" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        </div>
        <input className="in" placeholder={kind === 'income' ? '内容' : 'お店'} value={payee} onChange={(e) => setPayee(e.target.value)} />
        <input className="in" placeholder="メモ" value={memo} onChange={(e) => setMemo(e.target.value)} />
        <label className="field"><span>繰り返し</span>
          <select className="in" value={freq} onChange={(e) => setFreq(e.target.value)}>{FREQ.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label className="check-line"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />{' このお店を次からもこのカテゴリにする'}</label>
      </div>
    </Sheet>
  );
}

export async function openInput(after?: () => void): Promise<void> {
  let bk: Bk;
  try {
    bk = await get<Bk>('/api/book/accounts');
    if (!bk.accounts.some((a) => a.can_edit)) {
      const ok = await confirmBox('財布を作りますか？', '入力する口座がありません', '作る');
      if (!ok) return;
      await post('/api/book/accounts', { kind: 'cash', label: '財布' });
      bk = await get<Bk>('/api/book/accounts', { fresh: true });
    }
  } catch (e) { errorToast(e); return; }
  bookSheet(bk, (close) => <InputSheet close={() => close()} after={after} />);
}

// ------------------------------------------------------------------ 家計簿（収支・予算・推移）
function Donut({ groups, total }: { groups: any[]; total: number }) {
  const bk = useBk();
  const r = 46;
  const c = 2 * Math.PI * r;
  let off = 0;
  const segs: ReactNode[] = [];
  for (const g of groups) {
    if (g.amount <= 0 || total <= 0) continue;
    const len = (g.amount / total) * c;
    segs.push(<circle key={g.category} cx={60} cy={60} r={r} fill="none" stroke={catColor(bk, g.category)} strokeWidth={18}
      strokeDasharray={`${Math.max(0, len - 1)} ${c - len + 1}`} strokeDashoffset={-off} transform="rotate(-90 60 60)" />);
    off += len;
  }
  return (
    <svg viewBox="0 0 120 120" className="donut" role="img" aria-label="支出の内訳">
      <circle cx={60} cy={60} r={r} fill="none" stroke="#eeeae7" strokeWidth={18} />
      {segs}
    </svg>
  );
}

// 期日の来た繰り返しを記録する。表示を待たせない（入ったときだけ、読んでいる画面に取り直させる）
let recurringRan = 0;
function runRecurring() {
  if (Date.now() - recurringRan < 60000) return;
  recurringRan = Date.now();
  post('/api/book/recurring/run', {}, { keepCache: true }).then((r) => {
    if (r && r.added) forgetCache();
  }).catch(() => { /* 表示は続ける */ });
}

function summaryPath() {
  const q = new URLSearchParams({ month: month() });
  if (owner()) q.set('owner', owner());
  return `/api/book/summary?${q}`;
}
function budgetPath() { return `/api/book/budget?month=${month()}`; }
function trendPath() {
  const q = new URLSearchParams({ months: '12', month: month() });
  if (owner()) q.set('owner', owner());
  return `/api/book/trend?${q}`;
}
// 家計簿の最初の画面と、タブ（予算・推移）を先に取っておく
export function prefetchBook(): void {
  prefetch(['/api/book/accounts', '/api/book/status', summaryPath(), budgetPath(), trendPath()]);
}
warmers.push(prefetchBook);

function CatRow({ g, total }: { g: any; total: number }) {
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const has = g.children.length > 0;
  return (
    <div className="cat-row-wrap">
      <button type="button" className="cat-row" onClick={() => { if (has) setOpen(!open); else nav(`/txns/cat/${enc(g.category)}`); }}>
        <CatIcon acc={g.category} size={18} /><span className="cr-name">{isUncat(g.category) ? <b className="warn-text">{g.label}</b> : g.label}</span>
        <span className="cr-pct muted">{total ? `${Math.round((g.amount / total) * 100)}%` : ''}</span><span className="cr-amt num">{fmt(g.amount)}</span>
        <Icon name={has ? 'chevronDown' : 'chevronRight'} size={15} cls="muted" />
      </button>
      {has ? (
        <div className="cat-kids" hidden={!open}>
          {g.children.map((c: any) => <Link className="cat-kid" key={c.category} to={`/txns/cat/${enc(c.category)}`}><span>{c.label}</span><span className="num">{fmt(c.amount)}</span></Link>)}
          <Link className="cat-kid all" to={`/txns/cat/${enc(g.category)}`}>入出金を見る</Link>
        </div>
      ) : null}
    </div>
  );
}

function FlowView({ sum, stt }: { sum: any; stt: any }) {
  const exp = sum.categories.filter((g: any) => g.kind === 'expense');
  const inc = sum.categories.filter((g: any) => g.kind === 'income');
  return (
    <>
      <MonthBar /><OwnerChips />
      {stt.pending ? <Link className="band" to="/txns/pending"><Icon name="inbox" size={17} /><span>{`登録待ち ${stt.pending}件`}</span><Icon name="chevronRight" size={15} /></Link> : null}
      {sum.uncategorized ? <Link className="band soft" to="/txns/uncategorized"><Icon name="question" size={17} /><span>{`未分類 ${sum.uncategorized}件`}</span><Icon name="chevronRight" size={15} /></Link> : null}
      {sum.count === 0 ? (
        <div className="card empty"><Icon name="pie" size={30} /><b>まだ入出金がありません</b>
          <div className="row" style={{ justifyContent: 'center', gap: '8px', marginTop: '10px' }}>
            <button type="button" className="btn primary" onClick={() => { openInput(); }}><Icon name="plus" size={15} />入力</button>
            <Link className="btn" to="/settings/agents"><Icon name="layers" size={15} />連携</Link>
          </div>
        </div>
      ) : (
        <>
          <div className="kpi3">
            <div><small>収入</small><b className="num in">{fmt(sum.income)}</b></div>
            <div><small>支出</small><b className="num">{fmt(sum.expense)}</b></div>
            <div><small>収支</small><b className={`num ${sum.net < 0 ? 'neg' : 'in'}`}>{signed(sum.net)}</b></div>
          </div>
          {exp.length ? (
            <div className="card book-card">
              <div className="donut-wrap"><Donut groups={exp} total={sum.expense} /><div className="donut-center"><small>支出</small><b className="num">{fmt(sum.expense)}</b></div></div>
              <div className="cat-rows">{exp.map((g: any) => <CatRow key={g.category} g={g} total={sum.expense} />)}</div>
            </div>
          ) : null}
          {inc.length ? <div className="card book-card"><div className="section-title">収入</div><div className="cat-rows">{inc.map((g: any) => <CatRow key={g.category} g={g} total={sum.income} />)}</div></div> : null}
          {sum.excluded ? <p className="muted" style={{ fontSize: '12.5px' }}>{`計算対象外 ${sum.excluded}件は含めていません`}</p> : null}
        </>
      )}
    </>
  );
}

function BudgetBar({ spent, total }: { spent: number; total: number }) {
  const pct = total > 0 ? Math.min(100, (spent / total) * 100) : 0;
  return <div className={`bbar ${spent > total ? 'over' : pct > 85 ? 'near' : ''}`} role="img" aria-label={`${Math.round(total ? (spent / total) * 100 : 0)}%`}><i style={{ width: `${pct}%` }} /></div>;
}

function BudgetSheet({ b, close, after }: { b: any; close: () => void; after?: After }) {
  const bk = useBk();
  const tops = bk.categories.filter((c) => c.kind === 'expense' && !c.parent && !c.hidden && !isUncat(c.account));
  const [vals, setVals] = useState<Record<string, string>>(() => {
    const cur: Record<string, any> = Object.fromEntries(b.categories.map((c: any) => [c.category, c.budget]));
    return Object.fromEntries(tops.map((c) => [c.account, cur[c.account] ? fmt(cur[c.account]) : '']));
  });
  const total = tops.reduce((a, c) => a + (digits(vals[c.account] || '') || 0), 0);
  const save = async () => {
    const items = tops.map((c) => ({ category: c.account, amount: digits(vals[c.account] || '') || null }));
    try { await post('/api/book/budget', { items }); close(); toast('保存しました'); after && after(); } catch (e) { errorToast(e); }
  };
  return (
    <Sheet title="予算を設定する" onClose={close} footer={<button type="button" className="btn primary big" onClick={save}>保存</button>}>
      <div className="stack">
        <div className="row" style={{ justifyContent: 'space-between' }}><span>合計</span><b className="num">{`${fmt(total)}円`}</b></div>
        {tops.map((c) => (
          <label className="budget-edit" key={c.account}><CatIcon acc={c.account} size={16} /><span className="grow">{c.label}</span>
            <input className="in budget-in" inputMode="numeric" placeholder="—" value={vals[c.account] || ''} onChange={(e) => setVals({ ...vals, [c.account]: e.target.value })} /></label>
        ))}
      </div>
    </Sheet>
  );
}

function openBudget(bk: Bk, b: any, after?: After) {
  bookSheet(bk, (close) => <BudgetSheet b={b} close={() => close()} after={after} />);
}

function BudgetView({ b }: { b: any }) {
  const bk = useBk();
  if (!b.categories.length) {
    return (
      <>
        <MonthBar />
        <div className="card empty"><Icon name="wallet" size={30} /><b>予算がありません</b>
          <button type="button" className="btn primary" style={{ marginTop: '10px' }} onClick={() => openBudget(bk, b)}>予算を設定する</button></div>
      </>
    );
  }
  const over = b.remaining < 0;
  return (
    <>
      <MonthBar />
      <div className="card budget-total">
        <div className="row" style={{ justifyContent: 'space-between' }}><small className="muted">今月の予算</small>{b.days_left ? <small className="muted">{`残り ${b.days_left}日`}</small> : null}</div>
        <b className={`num ${over ? 'neg' : ''}`}>{over ? `${fmt(-b.remaining)}円オーバー` : `残り ${fmt(b.remaining)}円`}</b>
        <BudgetBar spent={b.spent} total={b.total} />
        <div className="row muted" style={{ justifyContent: 'space-between', fontSize: '12.5px' }}><span>{`使った額 ${fmt(b.spent)}円`}</span><span>{`予算 ${fmt(b.total)}円`}</span></div>
      </div>
      <div className="card book-card">{b.categories.map((c: any) => (
        <Link className="budget-row" key={c.category} to={`/txns/cat/${enc(c.category)}`}>
          <div className="row" style={{ gap: '10px' }}><CatIcon acc={c.category} size={16} /><span className="grow">{c.label}</span>
            <span className={`num ${c.remaining < 0 ? 'neg' : ''}`}>{c.remaining < 0 ? `${fmt(-c.remaining)}円オーバー` : `残り ${fmt(c.remaining)}`}</span></div>
          <BudgetBar spent={c.spent} total={c.budget} />
          <small className="muted">{`${fmt(c.spent)} / ${fmt(c.budget)}円`}</small>
        </Link>
      ))}</div>
      <div className="row" style={{ justifyContent: 'center' }}><button type="button" className="btn" onClick={() => openBudget(bk, b)}><Icon name="settings" size={15} />予算を設定する</button></div>
    </>
  );
}

// 推移：月ごとの収入・支出の棒（2系列。凡例・ホバーの値・表を付ける。色は検査済みの青・橙）
const C_IN = '#2a78d6';
const C_OUT = '#eb6834';

function TrendChart({ months }: { months: any[] }) {
  const [tip, setTip] = useState<number | null>(null);
  const W = 360, H = 180, L = 4, R = 4, T = 8, B2 = 22;
  const max = Math.max(1, ...months.flatMap((m) => [m.income, m.expense]));
  const ph = H - T - B2;
  const slot = (W - L - R) / months.length;
  const bw = Math.max(4, Math.min(14, slot / 2 - 2));
  const tm = tip !== null ? months[tip] : null;
  return (
    <div className="trend-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="trend-svg" role="img" aria-label="月ごとの収入と支出">
        <line x1={L} x2={W - R} y1={T + ph} y2={T + ph} stroke="#d6d3d1" strokeWidth={1} />
        {months.map((m, i) => {
          const cx = L + slot * i + slot / 2;
          const bars: Array<[number, string, number]> = [[m.income, C_IN, -1], [m.expense, C_OUT, 1]];
          return (
            <Fragment key={m.month}>
              {bars.map(([v, col, side]) => {
                const hgt = v > 0 ? Math.max(2, (v / max) * ph) : 0;
                const x = cx + (side < 0 ? -bw - 1 : 1);
                const rr = Math.min(4, bw / 2, hgt);
                return hgt ? <path key={side} d={`M${x} ${T + ph}V${T + ph - hgt + rr}a${rr} ${rr} 0 0 1 ${rr} -${rr}h${bw - 2 * rr}a${rr} ${rr} 0 0 1 ${rr} ${rr}V${T + ph}Z`} fill={col} /> : null;
              })}
              <text x={cx} y={H - 7} textAnchor="middle" fontSize={10} fill="#78716c">{`${Number(m.month.slice(5))}月`}</text>
              <rect x={L + slot * i} y={T} width={slot} height={ph} fill="transparent" onPointerEnter={() => setTip(i)} onPointerLeave={() => setTip((t) => (t === i ? null : t))} />
            </Fragment>
          );
        })}
      </svg>
      <div className="trend-tip" hidden={!tm} style={tm && tip !== null ? { left: `${((L + slot * tip + slot / 2) / W) * 100}%` } : undefined}>
        {tm ? (
          <>
            <b>{monthLabel(tm.month)}</b>
            <div><i className="sw" style={{ background: C_IN }} />{`収入 ${fmt(tm.income)}`}</div>
            <div><i className="sw" style={{ background: C_OUT }} />{`支出 ${fmt(tm.expense)}`}</div>
            <div>{`収支 ${signed(tm.net)}`}</div>
          </>
        ) : null}
      </div>
    </div>
  );
}

function TrendView({ t }: { t: any }) {
  const any = t.months.some((m: any) => m.income || m.expense);
  return (
    <>
      <MonthBar /><OwnerChips />
      {any ? (
        <>
          <div className="card book-card">
            <div className="legend"><span><i className="sw" style={{ background: C_IN }} />収入</span><span><i className="sw" style={{ background: C_OUT }} />支出</span></div>
            <TrendChart months={t.months} />
          </div>
          <div className="table-wrap"><table className="t">
            <thead><tr><th>月</th><th className="num">収入</th><th className="num">支出</th><th className="num">収支</th></tr></thead>
            <tbody>{[...t.months].reverse().map((m: any) => (
              <tr key={m.month} onClick={() => { setMonth(m.month); setPick('tab', 'flow'); }} style={{ cursor: 'pointer' }}>
                <td>{monthLabel(m.month)}</td><td className="num">{fmt(m.income)}</td><td className="num">{fmt(m.expense)}</td>
                <td className={`num ${m.net < 0 ? 'neg' : ''}`}>{signed(m.net)}</td>
              </tr>
            ))}</tbody>
          </table></div>
        </>
      ) : <div className="card empty"><Icon name="chart" size={30} /><b>まだ入出金がありません</b></div>}
    </>
  );
}

function BookBody() {
  const { month: m, owner: o, tab } = usePick();
  // 3つのタブの中身は並べて読む（先読みと同じ道。タブを切り替えても待たせない）
  const sumP = summaryPath(), budP = budgetPath(), trP = trendPath();
  const sum = useApi(sumP, { keep: true });
  const bud = useApi(budP, { keep: true });
  const tr = useApi(trP, { keep: true });
  const stt = useApi('/api/book/status');
  const sw = [useSwitching(sum, sumP), useSwitching(bud, budP), useSwitching(tr, trP)];
  useEffect(() => { runRecurring(); }, [tab, m, o]);
  const busy = tab === 'budget' ? sw[1] : tab === 'trend' ? sw[2] : sw[0];
  const wait = (q: { error: any }) => (q.error ? <ErrorNote error={q.error} /> : <Skeleton />);
  let body: ReactNode;
  if (tab === 'budget') body = bud.data ? <BudgetView b={bud.data} /> : wait(bud);
  else if (tab === 'trend') body = tr.data ? <TrendView t={tr.data} /> : wait(tr);
  else body = sum.data && stt.data ? <FlowView sum={sum.data} stt={stt.data} /> : wait(sum.error ? sum : stt);
  return (
    <div className={busy ? 'busy' : undefined} style={busy ? BUSY : undefined}>
      <div className="page-head"><h1>家計簿</h1></div>
      <div className="seg seg-wide" style={{ marginBottom: '12px' }}>
        {[['flow', '収支'], ['budget', '予算'], ['trend', '推移']].map(([k, l]) => <button type="button" key={k} className={tab === k ? 'on' : ''} onClick={() => setPick('tab', k)}>{l}</button>)}
      </div>
      {body}
      <button type="button" className="fab" aria-label="入力" onClick={() => { openInput(); }}><Icon name="plus" size={26} /></button>
    </div>
  );
}

export function BookPage() {
  return <WithBook><BookBody /></WithBook>;
}

// ------------------------------------------------------------------ 入出金（登録待ちを含む）
function TxnRow({ v, onClick, btn }: { v: any; onClick: () => void; btn?: ButtonHTMLAttributes<HTMLButtonElement> }) {
  const bk = useBk();
  const persons = useS((s) => s.persons);
  const name = v.payee || v.memo || catName(bk, v.category || v.transfer_to);
  const sub = v.transfer_to ? `振替 → ${(account(bk, v.transfer_to) || {}).label || ''}` : v.parts ? `分割 ${v.parts.length}件` : catName(bk, v.category);
  return (
    <button type="button" {...btn} className={`txn ${v.excluded ? 'excluded' : ''}`} onClick={onClick}>
      <CatIcon acc={v.category || v.transfer_to} size={17} view={v} />
      <span className="tx-main"><span className="tx-name">{name}</span>
        <small className="muted">{sub}{v.excluded ? ' ・計算対象外' : ''}{v.recurring ? ' ・繰り返し' : ''}{v.tax_record ? ' ・申告に使用' : ''}
          {persons && persons.length > 1 && v.owner_person ? ` ・${personName(v.owner_person)}` : ''}</small></span>
      <span className={amountClass(v)}>{signed(v.amount)}</span>
    </button>
  );
}

function DayGroups({ list, keyOf, render }: { list: any[]; keyOf: (v: any) => string; render: (v: any) => ReactNode }) {
  const days = new Map<string, any[]>();
  for (const v of list) { if (!days.has(v.date)) days.set(v.date, []); days.get(v.date)!.push(v); }
  return (
    <>{[...days.entries()].map(([d, vs]) => (
      <div className="day" key={d}>
        <div className="day-head"><span>{dayLabel(d)}</span><span className="num muted">{signed(vs.filter((x) => !x.transfer_to && !x.excluded).reduce((a, x) => a + x.amount, 0))}</span></div>
        <div className="day-rows">{vs.map((v) => <Fragment key={keyOf(v)}>{render(v)}</Fragment>)}</div>
      </div>
    ))}</>
  );
}

// 申告に使う：家計簿の入出金から、申告の記録（医療費の支払など）の入力を開く。確定は人が保存したとき
const TAX_KIND: Record<string, string> = { 医療費: 'medical_payment', 寄附金: 'donation', 社会保険料: 'social_insurance_payment', 小規模企業共済等掛金: 'mutual_aid_payment', 生命保険料: 'insurance_payment', 地震保険料: 'insurance_payment' };

function taxTarget(bk: Bk, v: any) {
  const lines = v.parts ? v.parts : [{ category: v.category, amount: Math.abs(v.amount) }];
  for (const l of lines) { const c = cat(bk, l.category); if (c && c.hint && TAX_KIND[c.hint]) return { hint: c.hint as string, kind: TAX_KIND[c.hint], amount: l.amount }; }
  return null;
}

async function openForTax(bk: Bk, v: any, after?: After) {
  const t = taxTarget(bk, v);
  if (!t) return;
  try { await loadMeta(); } catch (e) { errorToast(e); return; }
  const km = kindMeta(t.kind);
  if (!km) { toast('この種類の記録を入力できません', 'bad'); return; }
  const who = v.owner_person || (S.persons.find((p) => p.is_me) || ({} as any)).person_id;
  const init: any = { roles: {}, when: { on: v.date }, amounts: { amount: t.amount }, attributes: {} };
  if (t.kind === 'medical_payment') Object.assign(init, { roles: { payer: who, patient: who }, attributes: { incurred_on: v.date, provider: v.payee, medical_kinds: ['medical_treatment'] } });
  else if (t.kind === 'donation') Object.assign(init, { roles: { donor: who }, attributes: { recipient_name: v.payee } });
  else if (t.kind === 'social_insurance_payment') init.roles = { payer: who, liable_person: who };
  else if (t.kind === 'mutual_aid_payment') init.roles = { payer: who, member: who };
  else init.roles = { payer: who };
  await openRecordForm(km, init, async (saved?: any) => {
    if (!saved || !saved.record_id) return;
    try { await post(`/api/book/transactions/${enc(v.id)}/link`, { record_id: saved.record_id }); toast('申告の記録にしました'); after && after(); } catch (e) { errorToast(e); }
  });
}

function TxnSheet({ v, close, after }: { v: any; close: () => void; after?: After }) {
  const bk = useBk();
  const orig = v.category || v.transfer_to;
  const [category, setCategory] = useState<string | null>(orig || null);
  const [changed, setChanged] = useState(false);
  const [payee, setPayee] = useState<string>(v.payee || '');
  const [memo, setMemo] = useState<string>(v.memo || '');
  const [inCalc, setInCalc] = useState(!v.excluded);
  const [remember, setRemember] = useState(false);
  const a = account(bk, v.account) || {};
  const kind = v.amount > 0 ? 'income' : 'expense';
  const tax = taxTarget(bk, v);
  const del = async () => {
    const reason = await askText('取り消す理由', '理由', { placeholder: '例：二重に入っていた' });
    if (!reason) return;
    try { await post(`/api/book/transactions/${enc(v.id)}/delete`, { reason }); close(); toast('取り消しました'); after && after(); } catch (e) { errorToast(e); }
  };
  const save = async () => {
    const body: any = { payee, memo, excluded: !inCalc };
    if (!v.parts && category !== orig) { body.category = category; body.remember = remember; }
    try { await post(`/api/book/transactions/${enc(v.id)}/update`, body); close(); toast('保存しました'); after && after(); } catch (e) { errorToast(e); }
  };
  return (
    <Sheet title="入出金" onClose={close} footer={<>
      <button type="button" className="btn ghost danger-text" onClick={del}>取り消す</button><div className="grow" />
      <button type="button" className="btn primary" onClick={save}>保存</button></>}>
      <div className="stack">
        <div className={`big-amt ${amountClass(v)}`}>{signed(v.amount)}<small>円</small></div>
        <div className="muted">{`${dayLabel(v.date)}・${a.label || ''}${v.recurring ? '・繰り返し' : ''}`}</div>
        {v.parts ? (
          <div className="split-view">{v.parts.map((p: any, i: number) => (
            <div className="row" style={{ gap: '8px' }} key={i}><CatIcon acc={p.category} size={14} /><span className="grow">{catName(bk, p.category)}</span><span className="num">{fmt(p.amount)}</span></div>
          ))}</div>
        ) : <CatButton value={category} onChange={(c) => { setCategory(c); setChanged(true); }} opts={() => ({ kind, fromAccount: v.account })} />}
        <label className="check-line" hidden={!(changed && v.payee)}><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />{' このお店を次からもこのカテゴリにする'}</label>
        {v.transfer_to ? null : (
          <div className="row" style={{ gap: '8px', flexWrap: 'wrap' }}>
            <button type="button" className="btn small" onClick={() => { close(); openSplit(bk, v, after); }}><Icon name="layers" size={14} />{v.parts ? '分割を直す' : '分割'}</button>
            {v.tax_record ? <Link className="chip ok" to={`/records/${enc(v.tax_record)}`}><Icon name="check" size={12} />申告に使用</Link>
              : tax ? <button type="button" className="btn small" onClick={() => { close(); openForTax(bk, v, after); }}><Icon name="file" size={14} />{`申告に使う（${tax.hint}）`}</button> : null}
          </div>
        )}
        <input className="in" value={payee} placeholder={v.amount > 0 ? '内容' : 'お店'} onChange={(e) => setPayee(e.target.value)} />
        <input className="in" value={memo} placeholder="メモ" onChange={(e) => setMemo(e.target.value)} />
        <label className="check-line"><input type="checkbox" checked={inCalc} onChange={(e) => setInCalc(e.target.checked)} />{' 計算対象'}</label>
      </div>
    </Sheet>
  );
}

function openTxn(bk: Bk, v: any, after?: After) {
  bookSheet(bk, (close) => <TxnSheet v={v} close={() => close()} after={after} />);
}

function SplitSheet({ v, close, after }: { v: any; close: () => void; after?: After }) {
  const bk = useBk();
  const total = Math.abs(v.amount);
  const kind = v.amount > 0 ? 'income' : 'expense';
  const [rows, setRows] = useState<SplitRow[]>(() => splitRows(total, v.parts || [{ category: v.category, amount: total }, { category: null, amount: 0 }]));
  const stop = async () => {
    const c = await pickCategory(bk, { kind, current: v.parts[0].category });
    if (!c) return;
    try { await post(`/api/book/transactions/${enc(v.id)}/split`, { parts: [{ category: c, amount: total }] }); close(); toast('分割をやめました'); after && after(); } catch (e) { errorToast(e); }
  };
  const save = async () => {
    let parts;
    try { parts = readSplit(rows, total); } catch (e: any) { toast(e.message, 'bad'); return; }
    try { await post(`/api/book/transactions/${enc(v.id)}/split`, { parts }); close(); toast('分割しました'); after && after(); } catch (e) { errorToast(e); }
  };
  return (
    <Sheet title={`分割（${fmt(total)}円）`} onClose={close} footer={<>
      {v.parts ? <button type="button" className="btn ghost" onClick={stop}>分割をやめる</button> : null}<div className="grow" />
      <button type="button" className="btn primary" onClick={save}>保存</button></>}>
      <SplitEditor total={total} kind={kind} rows={rows} setRows={setRows} />
    </Sheet>
  );
}

function openSplit(bk: Bk, v: any, after?: After) {
  bookSheet(bk, (close) => <SplitSheet v={v} close={() => close()} after={after} />);
}

// 元に戻す（登録・対象外のあと数秒）。トーストの箱（#toasts）の中に、ボタン付きで出す
function UndoToast({ msg, items, after, close, box }: { msg: string; items: any[]; after?: After; close: () => void; box: HTMLElement }) {
  useEffect(() => { const t = setTimeout(() => close(), 7000); return () => clearTimeout(t); }, [close]);
  return createPortal(
    <div className="toast undo-toast"><span>{msg}</span><button type="button" className="btn small" onClick={async () => {
      close();
      try { await post('/api/book/pending/undo', { items }); toast('元に戻しました'); after && after(); } catch (e) { errorToast(e); }
    }}>元に戻す</button></div>, box);
}

function undoToast(msg: string, items: any[], after?: After) {
  const box = document.getElementById('toasts');
  if (!box) { toast(msg); return; }
  openOverlay((close) => <UndoToast msg={msg} items={items} after={after} close={() => close()} box={box} />, { persist: true });
}

// スワイプ（右＝登録、左＝対象外）。ボタンも画面に出しているので補助
function SwipeRow({ v, onClick, onRight, onLeft }: { v: any; onClick: () => void; onRight?: () => void; onLeft?: () => void }) {
  const g = useRef<{ x0: number | null; dx: number; id: number | null }>({ x0: null, dx: 0, id: null });
  const [shift, setShift] = useState<number | null>(null);
  const end = () => {
    const s = g.current;
    if (s.x0 === null) return;
    const d = s.dx; s.x0 = null; s.dx = 0;
    setShift(null);
    if (d > 90 && onRight) onRight();
    else if (d < -90 && onLeft) onLeft();
  };
  return (
    <div className={`swipe${shift !== null && shift > 0 ? ' right' : ''}${shift !== null && shift < 0 ? ' left' : ''}`}>
      <div className="sw-bg"><span className="sw-r"><Icon name="check" size={16} />登録</span><span className="sw-l">対象外<Icon name="x" size={16} /></span></div>
      <TxnRow v={v} onClick={onClick} btn={{
        style: shift !== null ? { transform: `translateX(${shift}px)` } : undefined,
        onPointerDown: (e) => { if (e.pointerType === 'mouse') return; g.current = { x0: e.clientX, dx: 0, id: e.pointerId }; },
        onPointerMove: (e) => {
          const s = g.current;
          if (s.x0 === null || e.pointerId !== s.id) return;
          s.dx = e.clientX - s.x0;
          if (Math.abs(s.dx) > 8) setShift(s.dx);
        },
        onPointerUp: end,
        onPointerCancel: end,
      }} />
    </div>
  );
}

function PendingSheet({ it, close, after }: { it: any; close: () => void; after?: After }) {
  const [category, setCategory] = useState<string | null>(it.category || null);
  const [remember, setRemember] = useState(false);
  const key = { batch: it.batch, source_id: it.source_id };
  const act = async (path: string, extra: any) => {
    try {
      await post(`/api/book/pending/${path}`, { items: [{ ...key, ...extra }] });
      close();
      undoToast(path === 'register' ? '登録しました' : '対象外にしました', [key], after);
      after && after();
    } catch (e) { errorToast(e); }
  };
  return (
    <Sheet title="登録待ち" onClose={close} footer={<>
      <button type="button" className="btn" onClick={() => act('ignore', {})}>対象外</button><div className="grow" />
      <button type="button" className="btn primary" onClick={() => act('register', { category, remember })}>登録</button></>}>
      <div className="stack">
        <div className={`big-amt ${it.amount > 0 ? 'amt in' : 'amt'}`}>{signed(it.amount)}<small>円</small></div>
        <div className="muted">{`${dayLabel(it.date)}・${it.account_label}`}</div>
        <div><b>{it.payee || '（お店なし）'}</b>{it.memo ? <div className="muted">{it.memo}</div> : null}</div>
        <CatButton value={category} onChange={setCategory} opts={() => ({ kind: it.amount > 0 ? 'income' : 'expense', fromAccount: it.account })} />
        {it.payee ? <label className="check-line"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />{' このお店を次からもこのカテゴリにする'}</label> : null}
      </div>
    </Sheet>
  );
}

function openPending(bk: Bk, it: any, after?: After) {
  bookSheet(bk, (close) => <PendingSheet it={it} close={() => close()} after={after} />);
}

// 長押しで選ぶ（まとめて変更）
function useLongPress(fn: () => void) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fired = useRef(false);
  const cb = useRef(fn);
  cb.current = fn;
  const cancel = () => { if (timer.current) { clearTimeout(timer.current); timer.current = null; } };
  useEffect(() => cancel, []);
  const props: ButtonHTMLAttributes<HTMLButtonElement> = {
    onPointerDown: (e) => {
      if (e.button > 0) return;
      fired.current = false;
      cancel();
      timer.current = setTimeout(() => { timer.current = null; fired.current = true; cb.current(); }, 500);
    },
    onPointerUp: cancel,
    onPointerLeave: cancel,
    onPointerCancel: cancel,
    onPointerMove: (e) => { if (Math.abs(e.movementX) + Math.abs(e.movementY) > 6) cancel(); },
    onContextMenu: (e) => { if (fired.current) e.preventDefault(); },
  };
  /** 長押しの直後のクリックは捨てる */
  const swallow = () => { if (fired.current) { fired.current = false; return true; } return false; };
  return { props, swallow };
}

function TxnItem({ v, selecting, picked, onTap, onLong, onCheck }: { v: any; selecting: boolean; picked: boolean; onTap: () => void; onLong: () => void; onCheck: (on: boolean) => void }) {
  const lp = useLongPress(onLong);
  const row = <TxnRow v={v} btn={lp.props} onClick={() => { if (lp.swallow()) return; onTap(); }} />;
  if (!selecting) return row;
  return <div className="txn-sel"><input type="checkbox" checked={picked} aria-label="選ぶ" onChange={(e) => onCheck(e.target.checked)} />{row}</div>;
}

function TxnChips({ mode, arg }: { mode: string; arg: string }) {
  const bk = useBk();
  const stt = useApi('/api/book/status');
  const pending = stt.data ? stt.data.pending : 0;
  return (
    <div className="chips-row">
      <Link className={`pchip ${!mode ? 'on' : ''}`} to="/txns">すべて</Link>
      <Link className={`pchip ${mode === 'pending' ? 'on' : ''}`} to="/txns/pending"><Icon name="inbox" size={14} />登録待ち{pending ? <span className="badge">{String(pending)}</span> : null}</Link>
      <Link className={`pchip ${mode === 'uncategorized' ? 'on' : ''}`} to="/txns/uncategorized">未分類</Link>
      {mode === 'cat' ? <span className="pchip on">{catName(bk, arg)}<Link to="/txns" aria-label="解除"><Icon name="x" size={12} /></Link></span> : null}
      {mode === 'acct' ? <span className="pchip on">{(account(bk, arg) || {}).label || '口座'}<Link to="/txns" aria-label="解除"><Icon name="x" size={12} /></Link></span> : null}
    </div>
  );
}

const pendingKey = (it: any) => `${it.batch}\u0000${it.source_id}`;

function PendingList({ mode, arg }: { mode: string; arg: string }) {
  const bk = useBk();
  const q = useApi(`/api/book/pending${mode === 'ignored' ? '?state=ignored' : ''}`);
  const [sel, setSel] = useState<Set<string>>(() => new Set());
  const head = <div className="page-head"><h1>入出金</h1></div>;
  const chips = <TxnChips mode={mode} arg={arg} />;
  if (!q.data) return <>{head}{chips}{q.error ? <ErrorNote error={q.error} /> : <Skeleton />}</>;
  const r = q.data;
  // 登録・対象外のあと：選んだ印を外し、件数（ナビの印）を取り直す。一覧は自動で取り直される
  const after = () => { setSel(new Set()); refreshStatus(); };
  const picked = r.items.filter((it: any) => sel.has(pendingKey(it)));
  const total = picked.reduce((a: number, x: any) => a + x.amount, 0);
  const registerAll = async () => {
    const ok = await confirmBox('まとめて登録', `${picked.length}件（合計 ${signed(total)}円）を登録します`, '登録');
    if (!ok) return;
    const items = picked.map((it: any) => ({ batch: it.batch, source_id: it.source_id }));
    try {
      await post('/api/book/pending/register', { items: picked.map((it: any) => ({ batch: it.batch, source_id: it.source_id, category: it.category })) });
      undoToast(`${picked.length}件を登録しました`, items, after);
      after();
    } catch (e) { errorToast(e); }
  };
  const quick = async (it: any, path: string) => {
    const k = { batch: it.batch, source_id: it.source_id };
    try {
      await post(`/api/book/pending/${path}`, { items: [path === 'register' ? { ...k, category: it.category } : k] });
      undoToast(path === 'register' ? '登録しました' : '対象外にしました', [k], after);
      after();
    } catch (e) { errorToast(e); }
  };
  const rowFor = (it: any) => {
    const can = !!it.category;
    const key = pendingKey(it);
    const v = { ...it, category: it.category || (it.amount > 0 ? 'Income:Uncategorized' : 'Expenses:Uncategorized') };
    if (mode === 'ignored') {
      return <div className="txn-sel"><TxnRow v={v} onClick={() => { post('/api/book/pending/restore', { items: [{ batch: it.batch, source_id: it.source_id }] }).then(() => { toast('登録待ちに戻しました'); }).catch(errorToast); }} /></div>;
    }
    return (
      <div className="txn-sel">
        <input type="checkbox" disabled={!can} aria-label="選ぶ" checked={sel.has(key)} onClick={(e) => e.stopPropagation()} onChange={(e) => {
          const on = e.target.checked;
          if (on && sel.size >= MAX_BULK) { toast(`一度に${MAX_BULK}件まで`, 'bad'); return; }
          setSel((prev) => { const n = new Set(prev); if (on) n.add(key); else n.delete(key); return n; });
        }} />
        <SwipeRow v={v} onClick={() => openPending(bk, it, after)} onRight={can ? () => { quick(it, 'register'); } : () => openPending(bk, it, after)} onLeft={() => { quick(it, 'ignore'); }} />
      </div>
    );
  };
  return (
    <>
      {head}{chips}
      {mode === 'pending' && r.items.length ? (
        <div className="row" style={{ justifyContent: 'space-between', margin: '4px 0 8px' }}>
          <span className="muted" style={{ fontSize: '12.5px' }}>{`${r.items.length}件`}</span><Link className="muted" to="/txns/ignored" style={{ fontSize: '12.5px' }}>対象外にしたもの</Link>
        </div>
      ) : null}
      {r.items.length ? <DayGroups list={r.items} keyOf={pendingKey} render={rowFor} />
        : <div className="card empty"><Icon name="checkCircle" size={30} /><b>{mode === 'pending' ? 'すべて登録済み' : '対象外はありません'}</b></div>}
      <div className="bulk-bar" hidden={!picked.length}>
        <span>{`${picked.length}件・${signed(total)}円`}</span><div className="grow" />
        <button type="button" className="btn primary" onClick={registerAll}>{`まとめて登録（${picked.length}件）`}</button>
      </div>
    </>
  );
}

function TxnList({ mode, arg }: { mode: string; arg: string }) {
  const bk = useBk();
  const { month: m, owner: o } = usePick();
  const [search, setSearch] = useState('');
  const [qtext, setQtext] = useState('');
  const [sel, setSel] = useState<Set<string>>(() => new Set());
  const [selecting, setSelecting] = useState(false);
  useEffect(() => { const t = setTimeout(() => setQtext(search.trim()), 250); return () => clearTimeout(t); }, [search]);

  const qs = new URLSearchParams();
  if (mode !== 'acct' && mode !== 'cat') qs.set('month', m);
  if (mode === 'uncategorized') qs.set('category', 'uncategorized');
  if (mode === 'cat') { qs.set('category', arg); qs.set('month', m); }
  if (mode === 'acct') qs.set('account', arg);
  if (o) qs.set('owner', o);
  const base = qs.toString();
  if (qtext) qs.set('q', qtext);
  const path = `/api/book/transactions?${qs}`;
  const q = useApi(path, { keep: true });
  const busy = useSwitching(q, path);
  // 月・人を切り替えたら、選んでいたものは外す
  useEffect(() => { setSelecting(false); setSel(new Set()); }, [base]);

  const stopSelecting = () => { setSelecting(false); setSel(new Set()); };
  const toggle = (id: string, on: boolean, limit: number) => setSel((prev) => {
    const n = new Set(prev);
    if (!on) n.delete(id); else if (n.size < limit) n.add(id);
    return n;
  });
  const exclude = async () => {
    try { await post('/api/book/transactions/bulk', { ids: [...sel], excluded: true }); toast('計算対象外にしました'); stopSelecting(); } catch (e) { errorToast(e); }
  };
  const recat = async () => {
    const c = await pickCategory(bk, { kind: 'expense' });
    if (!c) return;
    try {
      const r = await post('/api/book/transactions/bulk', { ids: [...sel], category: c });
      toast(r.skipped ? `変更しました（分割・振替の ${r.skipped}件はそのまま）` : '変更しました');
      stopSelecting();
    } catch (e) { errorToast(e); }
  };
  const rows: any[] | null = q.data ? q.data.transactions : null;
  return (
    <div className={busy ? 'busy' : undefined} style={busy ? BUSY : undefined}>
      <div className="page-head"><h1>入出金</h1></div>
      {mode === 'acct' ? null : <MonthBar />}
      <TxnChips mode={mode} arg={arg} />
      <OwnerChips />
      <input className="in" type="search" style={{ marginBottom: '12px' }} placeholder="お店・メモで検索" value={search} onChange={(e) => setSearch(e.target.value)} />
      <div>
        {!rows ? (q.error ? <ErrorNote error={q.error} /> : <Skeleton />)
          : rows.length ? (
            <DayGroups list={rows} keyOf={(v) => v.id} render={(v) => (
              <TxnItem v={v} selecting={selecting} picked={sel.has(v.id)}
                onTap={() => { if (selecting) toggle(v.id, !sel.has(v.id), 100); else openTxn(bk, v); }}
                onLong={() => { setSelecting(true); toggle(v.id, true, Infinity); }}
                onCheck={(on) => toggle(v.id, on, Infinity)} />
            )} />
          ) : <div className="card empty"><Icon name="list" size={28} /><b>{search ? '該当なし' : 'まだ入出金がありません'}</b></div>}
      </div>
      <div className="bulk-bar" hidden={!selecting}>
        <span>{`${sel.size}件`}</span><div className="grow" />
        <button type="button" className="btn ghost" onClick={stopSelecting}>やめる</button>
        <button type="button" className="btn" disabled={!sel.size} onClick={exclude}>計算対象外</button>
        <button type="button" className="btn primary" disabled={!sel.size} onClick={recat}>カテゴリを変更</button>
      </div>
      <button type="button" className="fab" aria-label="入力" onClick={() => { openInput(); }}><Icon name="plus" size={26} /></button>
    </div>
  );
}

export function TxnsPage() {
  const { mode = '', arg = '' } = useParams();
  useEffect(() => { runRecurring(); }, [mode, arg]);
  const pendingMode = mode === 'pending' || mode === 'ignored';
  return (
    <WithBook>
      {pendingMode ? <PendingList key={mode} mode={mode} arg={arg} /> : <TxnList key={`${mode}/${arg}`} mode={mode} arg={arg} />}
    </WithBook>
  );
}

// ------------------------------------------------------------------ 口座
function AccountSheet({ a, close, after }: { a: any; close: () => void; after?: After }) {
  const persons = useS((s) => s.persons);
  const me = useS((s) => s.me);
  const owners = persons.filter((p) => p.is_mine || me.role === 'admin');
  const [label, setLabel] = useState<string>(a.label || '');
  const [shared, setShared] = useState(!!a.shared);
  const [ownerSel, setOwnerSel] = useState<string>(owners.some((p) => p.person_id === a.owner_person) ? a.owner_person : '');
  const save = async () => {
    try {
      await post(`/api/book/accounts/${enc(a.account)}/update`, { label, shared, owner_person: ownerSel || null });
      close(); toast('保存しました'); after && after();
    } catch (e) { errorToast(e); }
  };
  return (
    <Sheet title={a.label} onClose={close} footer={a.can_edit ? <button type="button" className="btn primary" onClick={save}>保存</button> : undefined}>
      <div className="stack">
        <div className="big-amt">{signed(a.balance)}<small>円</small></div>
        {a.check && !a.check.ok ? <div className="note warn"><Icon name="alert" size={15} />{`残高が合わない（${a.check.date} の取得：${signed(a.check.reported)}円）`}</div> : null}
        <div className="row" style={{ gap: '8px', flexWrap: 'wrap' }}>
          {a.can_edit ? <button type="button" className="btn" onClick={() => { reconcile(a, () => { close(); after && after(); }); }}><Icon name="scale" size={15} />残高を調整</button> : null}
          <Link className="btn" to={`/txns/acct/${enc(a.account)}`} onClick={() => close()}><Icon name="list" size={15} />入出金</Link>
        </div>
        {a.can_edit ? (
          <>
            <label className="field"><span>名前</span><input className="in" value={label} onChange={(e) => setLabel(e.target.value)} /></label>
            <label className="field"><span>持ち主</span>
              <select className="in" value={ownerSel} onChange={(e) => setOwnerSel(e.target.value)}>
                <option value="">家族の共有（持ち主なし）</option>
                {owners.map((p) => <option key={p.person_id} value={p.person_id}>{p.display_name}</option>)}
              </select></label>
            <label className="check-line"><input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />{' 共有（家族も見られる）'}</label>
            <div className="muted" style={{ fontSize: '12px' }}><Icon name="lock" size={12} />{' 共有しない口座は、ほかの家族には名前も残高も見えません'}</div>
          </>
        ) : null}
      </div>
    </Sheet>
  );
}

function openAccount(a: any, after?: After) {
  openSheet((close) => <AccountSheet a={a} close={() => close()} after={after} />);
}

function ReconcileBody({ a, out }: { a: any; out: { current: number | null } }) {
  const [cur, setCur] = useState('');
  const [minus, setMinus] = useState(a.balance < 0);
  const n = digits(cur);
  const v = Number.isNaN(n) ? null : (minus ? -n : n);
  useEffect(() => { out.current = v; }, [out, v]);
  return (
    <div className="stack">
      <div className="muted">{`アプリの残高：${signed(a.balance)}円`}</div>
      <div className="amount-row"><span>¥</span><input className="in amount-in" inputMode="numeric" placeholder="今の残高" value={cur} onChange={(e) => setCur(e.target.value)} /></div>
      {a.kind === 'card' || a.balance < 0 ? <label className="check-line"><input type="checkbox" checked={minus} onChange={(e) => setMinus(e.target.checked)} />{' マイナス（カードの未払いなど）'}</label> : null}
      <div className="muted">{v === null ? '' : v === a.balance ? '残高が一致' : `差額 ${signed(v - a.balance)}円を使途不明金として記録`}</div>
    </div>
  );
}

async function reconcile(a: any, after: After) {
  const out: { current: number | null } = { current: null };
  const ok = await modal<boolean>('残高を調整', <ReconcileBody a={a} out={out} />, [{ label: 'やめる', value: false }, { label: '記録', kind: 'primary', run: async () => {
    const v = out.current;
    if (v === null) { toast('今の残高を入れてください', 'bad'); return false; }
    await post(`/api/book/accounts/${enc(a.account)}/reconcile`, { balance: v, date: today() });
    return true;
  } }]);
  if (ok) { toast('記録しました'); after(); }
}

type NewAccount = { kind: string; label: string; shared: boolean };

function AddAccountBody({ out }: { out: { current: NewAccount } }) {
  const [v, setV] = useState<NewAccount>(out.current);
  const set = (p: Partial<NewAccount>) => { const next = { ...v, ...p }; out.current = next; setV(next); };
  return (
    <div className="stack">
      <label className="field"><span>種類</span>
        <select className="in" value={v.kind} onChange={(e) => set({ kind: e.target.value })}>{Object.entries(KIND_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
      <label className="field"><span>名前</span><input className="in" placeholder="例：財布・〇〇銀行" value={v.label} onChange={(e) => set({ label: e.target.value })} /></label>
      <label className="check-line"><input type="checkbox" checked={v.shared} onChange={(e) => set({ shared: e.target.checked })} />{' 共有（家族も見られる）'}</label>
    </div>
  );
}

async function addAccount(after?: After) {
  const out: { current: NewAccount } = { current: { kind: Object.keys(KIND_LABEL)[0], label: '', shared: false } };
  const ok = await modal<boolean>('口座を追加', <AddAccountBody out={out} />,
    [{ label: 'やめる', value: false }, { label: '追加', kind: 'primary', run: async () => { await post('/api/book/accounts', out.current); return true; } }]);
  if (ok) { toast('追加しました'); after && after(); }
}

function AccountsBody() {
  const bk = useBk();
  const persons = useS((s) => s.persons);
  const accts = bk.accounts;
  const total = accts.reduce((a, x) => a + x.balance, 0);
  const groups = Object.keys(KIND_LABEL).map((k) => [k, accts.filter((a) => a.kind === k)] as [string, any[]]).filter(([, l]) => l.length);
  return (
    <>
      <div className="page-head"><h1>口座</h1><div className="grow" /><button type="button" className="btn" onClick={() => { addAccount(); }}><Icon name="plus" size={15} />口座を追加</button></div>
      {accts.length ? (
        <>
          <div className="card total-card"><small>資産総額</small><b className={`num ${total < 0 ? 'neg' : ''}`}>{signed(total)}<small>円</small></b></div>
          {groups.map(([k, list]) => (
            <div className="card acct-group" key={k}><div className="section-title"><Icon name={KIND_ICON[k]} size={15} />{KIND_LABEL[k]}</div>
              {list.map((a) => (
                <button type="button" className="acct-row" key={a.account} onClick={() => openAccount(a)}>
                  <span className="ar-name">{a.label}{a.shared ? null : <span className="muted" title="自分だけ"><Icon name="lock" size={13} /></span>}
                    {a.owner_person && persons.length > 1 ? <Avatar id={a.owner_person} name={personName(a.owner_person)} small /> : null}
                    {a.check && !a.check.ok ? <span className="chip warn">残高が合わない</span> : null}</span>
                  <span className="ar-right"><b className={`num ${a.balance < 0 ? 'neg' : ''}`}>{signed(a.balance)}</b>
                    {a.last_import ? <small className="muted">{`最終取得 ${a.last_import.slice(5, 16).replace('T', ' ')}`}</small> : null}</span>
                </button>
              ))}
            </div>
          ))}
        </>
      ) : (
        <div className="card empty"><Icon name="wallet" size={30} /><b>口座がありません</b>
          <button type="button" className="btn primary" style={{ marginTop: '10px' }} onClick={() => { addAccount(); }}><Icon name="plus" size={15} />口座を追加</button></div>
      )}
    </>
  );
}

export function AccountsPage() {
  return <WithBook><AccountsBody /></WithBook>;
}

// ------------------------------------------------------------------ カテゴリ・分類ルール（設定の中）
function CatSetTop({ t, kind }: { t: any; kind: string }) {
  const bk = useBk();
  const [open, setOpen] = useState(false);
  const kids = bk.categories.filter((c) => c.parent === t.account);
  const toggle = (c: any) => (
    <button type="button" className="btn ghost small" title={c.hidden ? '表示する' : '隠す'} onClick={async () => {
      try { await post(`/api/book/accounts/${enc(c.account)}/update`, { hidden: !c.hidden }); } catch (e) { errorToast(e); }
    }}><Icon name={c.hidden ? 'eyeOff' : 'eye'} size={15} /></button>
  );
  return (
    <details className="cat-set" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary><CatIcon acc={t.account} size={16} /><span className={t.hidden ? 'muted' : ''}>{t.label}</span><div className="grow" />{toggle(t)}</summary>
      {kids.map((c) => (
        <div className="cat-set-row" key={c.account}><span className={c.hidden ? 'muted' : ''}>{c.label}</span>{c.hint ? <span className="chip hint"><Icon name="file" size={12} />{c.hint}</span> : null}<div className="grow" />{toggle(c)}</div>
      ))}
      {kind === 'expense' ? (
        <button type="button" className="btn ghost small" onClick={async () => {
          const label = await askText(`${t.label} に追加`, '名前');
          if (!label) return;
          try { await post('/api/book/accounts', { kind, parent: t.account, label }); } catch (e) { errorToast(e); }
        }}><Icon name="plus" size={14} />追加</button>
      ) : null}
    </details>
  );
}

function CategoryBody() {
  const bk = useBk();
  const [kind, setKind] = useState(() => sessionStorage.getItem('okura.book.catkind') || 'expense');
  const rulesQ = useApi('/api/book/rules');
  const recQ = useApi('/api/book/recurring');
  if (!rulesQ.data || !recQ.data) {
    const err = rulesQ.error || recQ.error;
    return err ? <ErrorNote error={err} /> : <Skeleton />;
  }
  const rules: any[] = rulesQ.data.rules;
  const recurring: any[] = recQ.data.recurring;
  const tops = bk.categories.filter((c) => c.kind === kind && !c.parent);
  return (
    <>
      <div className="seg" style={{ marginBottom: '12px' }}>
        {[['expense', '支出'], ['income', '収入']].map(([k, l]) => <button type="button" key={k} className={kind === k ? 'on' : ''} onClick={() => { sessionStorage.setItem('okura.book.catkind', k); setKind(k); }}>{l}</button>)}
      </div>
      <div className="card">{tops.map((t) => <CatSetTop key={t.account} t={t} kind={kind} />)}</div>
      <h2>繰り返し</h2>
      <div className="card">{recurring.length ? recurring.map((r) => (
        <div className="cat-set-row" style={{ paddingLeft: 0 }} key={r.id}>
          <CatIcon acc={r.category} size={14} /><span>{r.payee || catName(bk, r.category)}</span><span className="muted">{`${(FREQ.find(([v]) => v === r.freq) || ['', ''])[1]}・${signed(r.amount)}円`}</span><div className="grow" />
          <button type="button" className="btn ghost small" onClick={async () => {
            if (!(await confirmBox('繰り返しを止めますか？', 'これまでに記録した入出金は残ります', '止める'))) return;
            try { await post(`/api/book/recurring/${enc(r.id)}/stop`, {}); } catch (e) { errorToast(e); }
          }}>止める</button>
        </div>
      )) : <div className="muted">まだありません（入力の「繰り返し」で作ります）</div>}</div>
      <h2>分類ルール</h2>
      <div className="card">
        {rules.length ? rules.map((r) => (
          <div className="cat-set-row" key={r.id}><span>{`「${r.pattern}」`}</span><Icon name="chevronRight" size={14} cls="muted" /><span>{catName(bk, r.category)}</span><div className="grow" />
            <button type="button" className="btn ghost small" title="外す" onClick={async () => { try { await post(`/api/book/rules/${enc(r.id)}/retire`, {}); } catch (e) { errorToast(e); } }}><Icon name="x" size={14} /></button></div>
        )) : <div className="muted">まだありません</div>}
        <button type="button" className="btn ghost small" style={{ marginTop: '8px' }} onClick={async () => {
          const pattern = await askText('分類ルールを追加', 'お店の文字（含む）', { placeholder: '例：スーパー' });
          if (!pattern) return;
          const c = await pickCategory(bk, { kind: 'expense' });
          if (!c) return;
          try { await post('/api/book/rules', { pattern, category: c }); } catch (e) { errorToast(e); }
        }}><Icon name="plus" size={14} />追加</button>
      </div>
    </>
  );
}

export function CategorySettings() {
  return <WithBook><CategoryBody /></WithBook>;
}
