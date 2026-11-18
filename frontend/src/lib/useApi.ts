// 読み取りのフック：記憶にあればすぐ出し、古ければ裏で取り直す。書き込みのあとは自動で取り直す
import { useCallback, useEffect, useRef, useState } from 'react';
import { get, peek, onInvalidate } from './api';

export type ApiState<T> = {
  data: T | undefined;
  error: Error | undefined;
  /** まだ1度も値がない */
  loading: boolean;
  /** 値はあるが取り直している（前の値を出したまま） */
  refreshing: boolean;
  reload: () => Promise<void>;
};

type Inner<T> = { path: string | null; data: T | undefined; error: Error | undefined; busy: boolean };

/**
 * @param path 読む API の道（null なら読まない）
 * @param opts.keep 道が変わったとき、新しい値が来るまで前の道の値を出したままにする（月・タブの切り替えでちらつかせない）
 */
export function useApi<T = any>(path: string | null, opts: { keep?: boolean } = {}): ApiState<T> {
  const keep = !!opts.keep;
  const [state, setState] = useState<Inner<T>>(() => {
    const hit = path ? peek<T>(path) : undefined;
    return { path, data: hit?.data, error: undefined, busy: !!path && !hit?.fresh };
  });
  const cur = useRef(path);
  cur.current = path;

  const load = useCallback(async (fresh: boolean) => {
    const p = cur.current;
    if (!p) return;
    setState((s) => ({ ...s, busy: true }));
    try {
      const d = await get<T>(p, { fresh });
      if (cur.current === p) setState({ path: p, data: d, error: undefined, busy: false });
    } catch (e) {
      if (cur.current === p) setState((s) => ({ path: p, data: s.path === p ? s.data : undefined, error: e as Error, busy: false }));
    }
  }, []);

  useEffect(() => {
    if (!path) { setState({ path, data: undefined, error: undefined, busy: false }); return undefined; }
    const hit = peek<T>(path);
    setState((s) => {
      if (hit) return { path, data: hit.data, error: undefined, busy: !hit.fresh };
      if (s.path === path) return { ...s, busy: true };
      return keep ? { ...s, error: undefined, busy: true } : { path, data: undefined, error: undefined, busy: true };
    });
    if (!hit?.fresh) load(false);
    return onInvalidate(() => { load(false); });
  }, [path, load, keep]);

  const reload = useCallback(() => load(true), [load]);
  // 道が変わった直後（effect の前）の描画でも、記憶にあればその値を出す
  const stale = state.path !== path;
  const hitNow = stale && path ? peek<T>(path) : undefined;
  const data = hitNow ? hitNow.data : (stale && !keep ? undefined : state.data);
  const busy = state.busy || (stale && !hitNow?.fresh);
  return { data, error: stale ? undefined : state.error, loading: data === undefined && !state.error && busy, refreshing: data !== undefined && busy, reload };
}
