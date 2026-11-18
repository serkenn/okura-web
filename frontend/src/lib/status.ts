// 状態の更新（計算中か・確認待ちの数・新しいバージョン）。15秒ごと（計算中は3秒ごと）に問い合わせる
import { useSyncExternalStore } from 'react';
import { get, post, ApiError, forgetCache, prefetch } from './api';
import { S, setS, loadLatest, loadMeta } from './store';
import { toast, errorToast } from '../ui/overlay';

let pollTimer: ReturnType<typeof setTimeout> | null = null;
let bootBuild: string | null = null;
let updateReady = false;
const subs = new Set<() => void>();

export function setBootBuild(b: string) { bootBuild = b; }
export function isUpdateReady() { return updateReady; }
export function useUpdateReady() {
  return useSyncExternalStore((fn) => { subs.add(fn); return () => { subs.delete(fn); }; }, () => updateReady);
}

function checkBuild(build: string | undefined) {
  if (!bootBuild) { bootBuild = build || null; return; }
  if (!build || build === bootBuild || updateReady) return;
  updateReady = true;
  for (const fn of [...subs]) fn();
}

// よく開く画面を新しく保つ道具（家計簿などが自分で登録する。開いたときに待たせない）
export const warmers: Array<() => void> = [];
export function warm() {
  for (const w of warmers) { try { w(); } catch { /* 先読みの失敗は黙る */ } }
  prefetch(['/api/records']);
  loadMeta().catch(() => {});
}

export async function refreshStatus(): Promise<void> {
  // 画面を見ていないあいだは問い合わせない（戻ったらすぐ問い合わせる）
  if (document.hidden) { if (pollTimer) clearTimeout(pollTimer); pollTimer = null; return; }
  try {
    get('/api/status').then((st) => checkBuild(st.build)).catch(() => {});
    const before = S.latest && S.latest.result ? S.latest.result.hash : null;
    const wasRunning = S.latest && S.latest.running;
    await loadLatest();
    const after = S.latest.result ? S.latest.result.hash : null;
    if (before !== after) forgetCache(); // 結果が変わったら、結果から作る読み取りの記憶を捨てる
    const [pr, ev, bk] = await Promise.all([
      get('/api/proposals', { fresh: true }),
      get('/api/evidence', { fresh: true }),
      get('/api/book/status', { fresh: true }).catch(() => ({ pending: 0 })),
    ]);
    const next = { bookPending: bk.pending || 0, proposals: pr.proposals.length, evidenceNew: ev.evidence.filter((e: any) => !e.records.length && !e.ignored).length };
    if (next.bookPending !== S.bookPending || next.proposals !== S.proposals || next.evidenceNew !== S.evidenceNew) setS(next);
    warm();
    if (wasRunning && !S.latest.running) {
      if (S.latest.last_job && S.latest.last_job.status === 'failed') toast(`計算エラー：${(S.latest.last_job.error || {}).message || ''}`, 'bad');
      else toast('再計算しました');
    }
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) { location.reload(); return; }
  }
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = setTimeout(refreshStatus, S.latest && S.latest.running ? 3000 : 15000);
}

export function startPolling() {
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !pollTimer) refreshStatus(); });
  refreshStatus();
}

export async function recalc() {
  try { await post('/api/calc', {}); toast('再計算しています（30秒ほど）'); await refreshStatus(); }
  catch (e) { errorToast(e); }
}

export async function logout() {
  try { await post('/api/logout', {}); } catch { /* 続ける */ }
  location.href = '/';
}
