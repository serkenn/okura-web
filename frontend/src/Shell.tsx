// 画面の枠組み（左のナビ・上のバー・スマホの下のタブ・Ctrl K の検索・計算の状態）
import { Component, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router';
import { NAV as L } from './lib/copy';
import { setNavigate } from './lib/nav';
import { S, useS } from './lib/store';
import { logout, recalc, useUpdateReady } from './lib/status';
import { Icon } from './ui/Icon';
import { Avatar, ErrorNote, Spinner } from './ui/bits';
import { closeOverlays, openOverlay, overlaysOpen } from './ui/overlay';
import { openAgent } from './views/Chat';

type NavItem = { path: string; ico: string; label: string; badge?: () => number } | { group: string };

function questionsCount() {
  const d = S.latest && S.latest.result && S.latest.result.digest;
  return d ? d.questions.filter((q: any) => q.means === '判断').length : 0;
}

const NAV: NavItem[] = [
  { path: 'home', ico: 'home', label: L.home },
  { group: '家計簿' },
  { path: 'book', ico: 'pie', label: L.book },
  { path: 'txns', ico: 'list', label: L.txns, badge: () => S.bookPending },
  { path: 'accounts', ico: 'wallet', label: L.accounts },
  { group: '税金・扶養' },
  { path: 'tax', ico: 'file', label: L.tax, badge: questionsCount },
  { path: 'upload', ico: 'camera', label: L.upload, badge: () => S.evidenceNew },
  { path: 'family', ico: 'users', label: L.family },
  { group: ' ' },
  { path: 'settings', ico: 'settings', label: L.settings },
];
const PAGES = NAV.filter((n): n is Extract<NavItem, { path: string }> => 'path' in n);

// ナビに出さない場所（状態の一覧と、申告の中の段）。入口は確定申告・ホーム・人・書類の中と、検索（Ctrl K）だけ
const MORE = [
  { path: 'inbox', ico: 'inbox', label: '確認待ち' },
  { path: 'records', ico: 'book', label: L.records },
  { path: 'questions', ico: 'question', label: L.questions },
  { path: 'forms', ico: 'file', label: L.forms },
];

// スマホの下のタブ（よく使う4つ＋その他）
const TABS = ['home', 'book', 'upload', 'tax'];
const TITLES: Record<string, string> = { ...L, evidence: L.upload, person: L.family, inbox: '確認待ち' };
// いまの場所が、ナビのどの項目の中か
const PARENT: Record<string, string> = { evidence: 'upload', person: 'family', questions: 'tax', forms: 'tax', records: 'tax', inbox: 'home' };

const to = (path: string) => (path === 'home' ? '/' : `/${path}`);

function useActive() {
  const { pathname } = useLocation();
  return pathname.split('/')[1] || 'home';
}

function SideNav({ active }: { active: string }) {
  const parent = PARENT[active] || active;
  return (
    <nav className="nav" aria-label="メニュー">
      {NAV.map((n, i) => {
        if ('group' in n) return <div className="group" key={i}>{n.group}</div>;
        const on = parent === n.path;
        const b = n.badge ? n.badge() : 0;
        return (
          <Link key={n.path} to={to(n.path)} className={on ? 'on' : ''} aria-current={on ? 'page' : undefined}>
            <Icon name={n.ico} size={17} />{n.label}{b ? <span className="badge">{String(b)}</span> : null}
          </Link>
        );
      })}
    </nav>
  );
}

function Tabbar({ active }: { active: string }) {
  const cur = active === 'inbox' ? 'inbox' : (PARENT[active] || active);
  const moreOn = !TABS.includes(cur);
  const moreBadge = S.bookPending || 0; // その他の中で件数があるのは入出金（登録待ち）だけ
  return (
    <nav className="tabbar" aria-label="メニュー">
      {TABS.map((p) => {
        const n = PAGES.find((x) => x.path === p)!;
        const b = n.badge ? n.badge() : 0;
        return (
          <Link key={p} to={to(p)} className={cur === p ? 'on' : ''}>
            <span className="tb-ico"><Icon name={n.ico} size={22} />{b ? <span className="tb-badge">{String(b)}</span> : null}</span>
            <span>{n.label}</span>
          </Link>
        );
      })}
      <button type="button" className={moreOn ? 'on' : ''} onClick={openMore}>
        <span className="tb-ico"><Icon name="dots" size={22} />{moreBadge ? <span className="tb-badge">{String(moreBadge)}</span> : null}</span>
        <span>{L.more}</span>
      </button>
    </nav>
  );
}

function openMore() {
  openOverlay((close) => (
    <div className="sheet-bg" onClick={(e) => { if (e.target === e.currentTarget) close(); }}>
      <div className="sheet">
        <div className="sheet-grip" />
        <div className="sheet-grid">
          {PAGES.filter((n) => !TABS.includes(n.path)).map((n) => {
            const b = n.badge ? n.badge() : 0;
            return (
              <Link key={n.path} to={to(n.path)} onClick={() => close()}>
                <span className="sg-ico"><Icon name={n.ico} size={22} />{b ? <span className="tb-badge">{String(b)}</span> : null}</span>{n.label}
              </Link>
            );
          })}
          <a href="/" onClick={(e) => { e.preventDefault(); close(); logout(); }}><span className="sg-ico"><Icon name="logout" size={22} /></span>ログアウト</a>
        </div>
      </div>
    </div>
  ));
}

function CalcPill() {
  const latest = useS((s) => s.latest);
  if (!latest) return <span className="chip">…</span>;
  if (latest.running) return <span className="chip info"><Spinner size={10} />計算中</span>;
  if (latest.last_job && latest.last_job.status === 'failed') return <span className="chip bad" title={(latest.last_job.error || {}).message || ''}>計算エラー</span>;
  if (!latest.result) return <span className="chip warn">未計算</span>;
  if (latest.result.stale) return <span className="chip warn" title="記録が変わりました">再計算が必要</span>;
  return <span className="chip ok" title={`計算した日時 ${(latest.result.finished_at || '').replace('T', ' ')}`}>最新</span>;
}

type PaletteItem = { ico: string; label: string; sub: string; run: () => void };

function Palette({ onClose }: { onClose: () => void }) {
  const nav = useNavigate();
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const items = useMemo<PaletteItem[]>(() => [
    ...[...PAGES, ...MORE].map((n) => ({ ico: n.ico, label: n.label, sub: 'ページ', run: () => nav(to(n.path)) })),
    { ico: 'upload', label: '書類をアップロード', sub: '操作', run: () => nav('/upload') },
    { ico: 'refresh', label: '再計算', sub: '操作', run: () => { recalc(); } },
    { ico: 'sparkles', label: 'AIに質問', sub: '操作', run: () => { openAgent(); } },
    { ico: 'lock', label: '共有設定', sub: '設定', run: () => nav('/settings/consents') },
    { ico: 'building', label: '市区町村・保険の設定', sub: '設定', run: () => nav('/settings/injections') },
    { ico: 'key', label: 'AI連携', sub: '設定', run: () => nav('/settings/agents') },
    ...S.persons.map((p) => ({ ico: 'users', label: p.display_name, sub: '家族', run: () => nav(`/person/${encodeURIComponent(p.person_id)}`) })),
  ], [nav]);
  const query = q.trim();
  const shown = items.filter((i) => !query || i.label.includes(query) || i.sub.includes(query));
  const cur = Math.min(sel, Math.max(0, shown.length - 1));
  const pick = (i: PaletteItem) => { onClose(); i.run(); };
  useEffect(() => { input.current?.focus(); }, []);
  return (
    <div className="palette-bg" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="palette">
        <input ref={input} type="text" placeholder="検索" aria-label="検索" value={q}
          onChange={(e) => { setQ(e.target.value); setSel(0); }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { setSel(Math.min(shown.length - 1, cur + 1)); e.preventDefault(); }
            else if (e.key === 'ArrowUp') { setSel(Math.max(0, cur - 1)); e.preventDefault(); }
            else if (e.key === 'Enter' && shown[cur]) pick(shown[cur]);
            else if (e.key === 'Escape') onClose();
          }} />
        <ul role="listbox">
          {shown.length ? shown.map((i, k) => (
            <li key={`${i.sub}:${i.label}`} className={k === cur ? 'on' : ''} onClick={() => pick(i)} onMouseEnter={() => setSel(k)}>
              <Icon name={i.ico} size={16} />{i.label}<span className="p-sub">{i.sub}</span>
            </li>
          )) : <li className="muted">見つからない</li>}
        </ul>
      </div>
    </div>
  );
}

let paletteOpen = false;
function openPalette() {
  if (paletteOpen) return;
  paletteOpen = true;
  openOverlay((close) => <Palette onClose={() => close()} />).finally(() => { paletteOpen = false; });
}

function UpdateBar() {
  const ready = useUpdateReady();
  if (!ready) return null;
  // 下に小さく出す。押せばすぐ、押さなくても次に画面を移るとき（入力・会話の途中でなければ）新しいバージョンにする
  return (
    <div className="update-bar" role="status">
      <span>新しいバージョン</span>
      <button type="button" className="ub-btn" onClick={() => location.reload()}>更新</button>
    </div>
  );
}

// 1つの画面が描けなくても、枠（メニュー）は残す。画面を移ると元に戻る
class ViewBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error) { console.warn(error.name); }
  render() { return this.state.error ? <ErrorNote error={{ message: '表示できませんでした' }} /> : this.props.children; }
}

export default function Shell() {
  const active = useActive();
  const loc = useLocation();
  const ready = useUpdateReady();
  const me = useS((s) => s.me);
  const household = useS((s) => s.household);
  const persons = useS((s) => s.persons);
  // 件数（バッジ）が変わったら描き直す
  useS((s) => `${s.bookPending}.${s.proposals}.${s.evidenceNew}`);
  useS((s) => s.latest);
  const first = useRef(true);
  const navigate = useNavigate();
  useEffect(() => { setNavigate((path, o) => navigate(path, o)); }, [navigate]);

  useEffect(() => {
    if (first.current) { first.current = false; return; }
    if (ready && !overlaysOpen()) { location.reload(); return; }
    closeOverlays();
    window.scrollTo(0, 0);
  }, [loc.pathname, ready]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette(); }
    };
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, []);

  const mine = persons.find((p) => p.is_me);
  return (
    <div className="shell">
      <aside className="side">
        <div className="brand"><img src="/icon.svg" alt="" /><div><b>{household.household.name}</b><small className="muted">okura-web</small></div></div>
        <SideNav active={active} />
        <div className="me">
          <Avatar id={mine ? mine.person_id : me.user.id} name={me.user.display_name} small />
          <div className="grow"><b>{me.user.display_name}</b><small className="muted">{me.role === 'admin' ? '管理者' : 'メンバー'}</small></div>
          <button type="button" className="btn ghost icon" onClick={logout} title="ログアウト" aria-label="ログアウト"><Icon name="logout" size={16} /></button>
        </div>
      </aside>
      <Tabbar active={active} />
      <div className="main">
        <div id="topbar">
          <header className="top">
            <span className="crumb">{TITLES[active] || ''}</span>
            <div className="grow" />
            <button type="button" className="search-btn" onClick={openPalette} aria-label="検索"><Icon name="search" size={15} /><span>検索</span><kbd>Ctrl K</kbd></button>
            <CalcPill />
            <button type="button" className="btn small" onClick={recalc} title="再計算"><Icon name="refresh" size={14} />再計算</button>
            <button type="button" className="btn small primary" onClick={() => openAgent()}><Icon name="sparkles" size={14} />AI</button>
          </header>
        </div>
        <div className="content" id="content"><ViewBoundary key={loc.pathname}><Outlet /></ViewBoundary></div>
        <footer className="foot">計算は okura-gov によるものです。申告の前に、内容を必ずご確認ください。データはこのパソコンにだけ保存されます。</footer>
      </div>
      <UpdateBar />
    </div>
  );
}
