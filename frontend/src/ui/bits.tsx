// 小さな部品（人の頭文字・状態の印・問題の一覧・待ちの表示・コピー）
import type { ReactNode } from 'react';
import { Icon } from './Icon';
import { toast } from './overlay';

// 人ごとの色の頭文字（ID から決める）
const AV_COLORS = ['#0d7a5f', '#6941c6', '#c4320a', '#175cd3', '#b54708', '#c11574', '#344054', '#087443'];
export function Avatar({ id, name, small = false }: { id: string | null | undefined; name: string | null | undefined; small?: boolean }) {
  let n = 0;
  for (const ch of String(id || '')) n = (n * 31 + ch.charCodeAt(0)) >>> 0;
  return <span className={`avatar ${small ? 'sm' : ''}`} style={{ background: AV_COLORS[n % AV_COLORS.length] }} aria-hidden="true">{(name || '?').trim().slice(0, 1)}</span>;
}

const CHIP_CLASS: Record<string, string> = { 未確定: 'undet', 対象外: 'oos', 予測: 'forecast', 見積り: 'info', 計画: 'info' };
const CHIP_LABEL: Record<string, string> = { 対象外: '未対応', 予測: '見込み', 計画: '予定' };
/** 値の状態（未確定・対象外・予測など）を消さずに印で出す */
export function StateChips({ states }: { states?: string[] | null }) {
  return <>{(states || []).map((s) => <span key={s} className={`chip ${CHIP_CLASS[s] || ''}`}>{CHIP_LABEL[s] || s}</span>)}</>;
}

export function ProblemsList({ detail }: { detail: any }) {
  if (!Array.isArray(detail) || !detail.length) return null;
  return (
    <ul className="muted" style={{ fontSize: '.85rem' }}>
      {detail.slice(0, 12).map((p: any, i: number) => <li key={i}>{`${p.where || p.path || ''}：${p.message || p.code}`}</li>)}
    </ul>
  );
}

export async function copyText(text: string) {
  try { await navigator.clipboard.writeText(text); toast('コピーした'); }
  catch { toast('コピーできなかった（ブラウザの許可）', 'bad'); }
}

/** 画面の中身を待つあいだの骨組み */
export function Skeleton() {
  return (
    <div className="stack late">
      <div className="skeleton" style={{ width: '30%', height: '24px' }} />
      <div className="skeleton" style={{ width: '60%' }} />
      <div className="skeleton" style={{ height: '120px', marginTop: '20px' }} />
    </div>
  );
}

export function Spinner({ size }: { size?: number }) {
  return <span className="spinner" style={size ? { width: `${size}px`, height: `${size}px` } : undefined} />;
}

/** 空・エラーのカード */
export function Empty({ icon, title, children }: { icon?: string; title: ReactNode; children?: ReactNode }) {
  return <div className="card empty">{icon ? <Icon name={icon} size={30} /> : null}<b>{title}</b>{children}</div>;
}

export function ErrorNote({ error }: { error: any }) {
  return <div className="note bad"><Icon name="alert" size={16} />{(error && error.message) || '表示できませんでした'}</div>;
}

/** 読み取りの結果（useApi）を待って中身を描く。値が1度来たら、取り直しのあいだも前の値を出したままにする */
export function Loaded<T>({ q, children }: { q: { data: T | undefined; error: Error | undefined }; children: (data: T) => ReactNode }) {
  if (q.data !== undefined) return <>{children(q.data)}</>;
  if (q.error) return <ErrorNote error={q.error} />;
  return <Skeleton />;
}
