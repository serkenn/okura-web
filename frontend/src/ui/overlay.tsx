// 重ねて出すもの（トースト・モーダル・ドロワー・シート）。
// どこからでも関数で開ける（await で答えを待てる）。描くのは <OverlayHost/>（App の中に1つ）。
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { Icon } from './Icon';

type Entry = { id: number; node: ReactNode; persist: boolean; close: (v?: any) => void };
type Toast = { id: number; msg: string; kind: string };

let entries: Entry[] = [];
let toasts: Toast[] = [];
let seq = 0;
let ver = 0;
const subs = new Set<() => void>();
const emit = () => { ver += 1; for (const fn of [...subs]) fn(); };
const subscribe = (fn: () => void) => { subs.add(fn); return () => { subs.delete(fn); }; };

/**
 * 重ねて出す。render には閉じる関数が渡る。閉じたときの値で Promise が解決する（外から閉じたときは null）。
 * persist: 画面を移っても閉じない（AI の会話など）
 */
export function openOverlay<T = any>(render: (close: (v?: T | null) => void) => ReactNode, opts: { persist?: boolean } = {}): Promise<T | null> & { close: (v?: T | null) => void } {
  const id = ++seq;
  let resolve!: (v: T | null) => void;
  const pr = new Promise<T | null>((r) => { resolve = r; }) as Promise<T | null> & { close: (v?: T | null) => void };
  let closed = false;
  const close = (v?: T | null) => {
    if (closed) return;
    closed = true;
    entries = entries.filter((e) => e.id !== id);
    emit();
    resolve(v === undefined ? null : v);
  };
  entries = [...entries, { id, node: render(close), persist: !!opts.persist, close }];
  emit();
  pr.close = close;
  return pr;
}

/** 画面を移ったとき：開いているもの（persist 以外）を閉じる */
export function closeOverlays() {
  for (const e of entries.filter((x) => !x.persist)) e.close(null);
}

/** 入力・会話の途中か（新しいバージョンへの自動の切り替えを待つ） */
export function overlaysOpen() { return entries.length > 0; }

export function toast(msg: string, kind = '') {
  const id = ++seq;
  toasts = [...toasts, { id, msg, kind }];
  emit();
  setTimeout(() => { toasts = toasts.filter((t) => t.id !== id); emit(); }, kind === 'bad' ? 7000 : 3500);
}

export function errorToast(e: any) {
  console.warn(e && e.code);
  toast(e && e.message ? e.message : 'うまくいかなかった', 'bad');
}

export function OverlayHost() {
  useSyncExternalStore(subscribe, () => ver);
  return (
    <>
      {entries.map((e) => <div key={e.id} style={{ display: 'contents' }}>{e.node}</div>)}
      <div id="toasts" role="status" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.msg}</div>)}
      </div>
    </>
  );
}

// ------------------------------------------------------------------ モーダル
export type ModalAction<T = any> = {
  label: string;
  kind?: string;
  /** run がないとき、押したらこの値で閉じる */
  value?: T;
  /** 押したときの処理。false を返すと閉じない。値を返すとその値で閉じる（undefined なら value） */
  run?: () => any | Promise<any>;
};

export function Modal({ title, children, actions = [], onClose, wide }: { title: string; children?: ReactNode; actions?: ModalAction[]; onClose: (v?: any) => void; wide?: boolean }) {
  const [busy, setBusy] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const f = box.current?.querySelector<HTMLElement>('input, select, textarea, button.primary');
    f?.focus();
  }, []);
  const press = async (a: ModalAction, i: number) => {
    if (!a.run) { onClose(a.value); return; }
    setBusy(i);
    try {
      const v = await a.run();
      if (v === false) return;
      onClose(v === undefined ? a.value : v);
    } catch (e) { errorToast(e); } finally { setBusy(null); }
  };
  return (
    <div className="modal-bg" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(null); }}>
      <div className="modal" role="dialog" aria-label={title} ref={box} style={wide ? { maxWidth: 'min(820px, 96vw)' } : undefined}>
        <h2>{title}</h2>
        {children}
        {actions.length ? (
          <div className="row end" style={{ marginTop: '16px' }}>
            {actions.map((a, i) => (
              <button key={i} type="button" className={`btn ${a.kind || ''}`} disabled={busy !== null} onClick={() => press(a, i)}>
                {busy === i ? '処理中…' : a.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * モーダルを開いて答えを待つ。body は中身（状態を持つならコンポーネントを渡す）。
 * actions の run の中で入力を読むときは、ref か、外の変数（body のコンポーネントから書く）を使う。
 */
export function modal<T = any>(title: string, body: ReactNode, actions: ModalAction<T>[] = [], opts: { wide?: boolean } = {}): Promise<T | null> {
  return openOverlay<T>((close) => <Modal title={title} actions={actions} onClose={close} wide={opts.wide}>{body}</Modal>);
}

export function confirmBox(title: string, text: ReactNode, okLabel = 'はい', kind = 'primary'): Promise<boolean> {
  return modal<boolean>(title, <p>{text}</p>, [{ label: 'やめる', value: false }, { label: okLabel, value: true, kind }]).then((v) => !!v);
}

export function askText(title: string, label: string, { placeholder = '', required = true, initial = '' }: { placeholder?: string; required?: boolean; initial?: string } = {}): Promise<string | null> {
  const ref = { current: null as HTMLInputElement | null };
  return modal<string>(title,
    <div className="field"><label>{label}</label><input type="text" className="in" placeholder={placeholder} defaultValue={initial} ref={(el) => { ref.current = el; }} /></div>,
    [
      { label: 'やめる', value: null as any },
      { label: '決める', kind: 'primary', run: () => {
        const v = (ref.current?.value || '').trim();
        if (required && !v) { ref.current?.focus(); return false; }
        return v;
      } },
    ]);
}

// ------------------------------------------------------------------ ドロワー（右から出る）
export function Drawer({ title, children, onClose, wide }: { title: string; children?: ReactNode; onClose: () => void; wide?: boolean }) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', esc);
    return () => document.removeEventListener('keydown', esc);
  }, [onClose]);
  return (
    <>
      <div className="drawer-bg" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={title} style={wide ? { width: 'min(900px, 98vw)' } : undefined}>
        <div className="d-head"><h2>{title}</h2><button type="button" className="btn ghost" onClick={onClose} aria-label="閉じる">✕</button></div>
        <div className="d-body">{children}</div>
      </aside>
    </>
  );
}

/** ドロワーを開く。render には閉じる関数が渡る */
export function openDrawer<T = any>(title: string, render: (close: (v?: T | null) => void) => ReactNode, opts: { wide?: boolean } = {}) {
  return openOverlay<T>((close) => <Drawer title={title} wide={opts.wide} onClose={() => close(null)}>{render(close)}</Drawer>);
}

// ------------------------------------------------------------------ シート（スマホでは下から。PC では中央）
export function Sheet({ title, children, footer, onClose }: { title: string; children?: ReactNode; footer?: ReactNode; onClose: () => void }) {
  return (
    <div className="sheet-bg book-sheet" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="sheet" role="dialog" aria-label={title}>
        <div className="sheet-grip" />
        <div className="sh-head"><b>{title}</b><button type="button" className="btn ghost small" onClick={onClose} aria-label="閉じる"><Icon name="x" size={16} /></button></div>
        <div className="sh-body">{children}</div>
        {footer ? <div className="sh-foot">{footer}</div> : null}
      </div>
    </div>
  );
}

/** シートを開く。render は { children, footer } を返すコンポーネントでもよい（中で <Sheet> を使う） */
export function openSheet<T = any>(render: (close: (v?: T | null) => void) => ReactNode) {
  return openOverlay<T>(render);
}
