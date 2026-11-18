// 起動と経路（React Router）
import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router';
import './app.css';
import { get, setCsrf, ApiError } from './lib/api';
import { setBootBuild, startPolling, warm } from './lib/status';
import { S, loadHousehold, loadLatest, loadMe } from './lib/store';
import Shell from './Shell';
import { OverlayHost } from './ui/overlay';
import { LoginPage, SetupPage } from './views/Auth';
import { BookPage, TxnsPage, AccountsPage } from './views/Book';
import { RecordsPage, FamilyPage } from './views/Data';
import { GuestPage, JoinPage } from './views/Guest';
import Home from './views/Home';
import { UploadPage, EvidencePage, InboxPage } from './views/Intake';
import { QuestionsPage, FormsPage, PersonPage } from './views/Results';
import { SettingsPage } from './views/Settings';
import { TaxPage } from './views/Tax';

// 古いリンク（#/tax/2026 など）を新しい道（/tax/2026）へ
if (location.hash.startsWith('#/')) history.replaceState(null, '', location.hash.slice(1) === '/home' ? '/' : location.hash.slice(1));

// 古い「計算結果」の画面は、確定申告（1人の申告の③結果）と人のページに移した
function OldResults() {
  const { pid } = useParams();
  return <Navigate replace to={pid ? `/person/${encodeURIComponent(pid)}` : '/tax'} />;
}

function AppRoutes() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Home />} />
        <Route path="home" element={<Navigate replace to="/" />} />
        <Route path="book" element={<BookPage />} />
        <Route path="txns/:mode?/:arg?" element={<TxnsPage />} />
        <Route path="accounts" element={<AccountsPage />} />
        <Route path="upload/:owner?" element={<UploadPage />} />
        <Route path="evidence/:eid" element={<EvidencePage />} />
        <Route path="inbox" element={<InboxPage />} />
        <Route path="records/:rid?" element={<RecordsPage />} />
        <Route path="family" element={<FamilyPage />} />
        <Route path="person/:pid" element={<PersonPage />} />
        <Route path="tax/:year?/:pid?/:step?" element={<TaxPage />} />
        <Route path="questions/:means?" element={<QuestionsPage />} />
        <Route path="forms/:person?/:year?" element={<FormsPage />} />
        <Route path="settings/:tab?/*" element={<SettingsPage />} />
        <Route path="results/:pid?" element={<OldResults />} />
        <Route path="*" element={<Navigate replace to="/" />} />
      </Route>
    </Routes>
  );
}

let booted = false; // 開発のとき（StrictMode）に2回動かさない

type Mode = 'boot' | 'setup' | 'login' | 'guest' | 'app' | { error: string };

function Boot() {
  const [join] = useState(() => (location.pathname.startsWith('/join/') ? location.pathname.slice('/join/'.length) : null));
  const [mode, setMode] = useState<Mode>('boot');
  useEffect(() => {
    if (join || booted) return;
    booted = true;
    (async () => {
      // 起動の問い合わせは並べて出す（順に待たない）
      const [st, me] = await Promise.all([get('/api/status'), loadMe().catch((e) => e)]);
      setBootBuild(st.build);
      if (!st.initialized) { setMode('setup'); return; }
      if (me instanceof Error) {
        if (me instanceof ApiError && me.code === 'guest_only') { setMode('guest'); return; }
        if (me instanceof ApiError && me.status === 401) { setMode('login'); return; }
        throw me;
      }
      setCsrf(S.me.csrf);
      await Promise.all([loadHousehold(), loadLatest()]);
      setMode('app');
      startPolling(); // 確認待ちの数などは後から
      (window.requestIdleCallback || ((f: () => void) => setTimeout(f, 300)))(() => warm());
    })().catch((e) => setMode({ error: e.message }));
  }, [join]);

  if (join) return <JoinPage token={join} />;
  if (mode === 'boot') return <div className="boot-skel" aria-hidden="true"><div className="sk sk-bar" /><div className="sk sk-title" /><div className="sk sk-card" /><div className="sk sk-card short" /></div>;
  if (mode === 'setup') return <SetupPage />;
  if (mode === 'login') return <LoginPage />;
  if (mode === 'guest') return <GuestPage />;
  if (mode === 'app') return <AppRoutes />;
  return <div className="content"><div className="note bad">{`起動できなかった：${mode.error}`}</div></div>;
}

createRoot(document.getElementById('app')!).render(
  <StrictMode>
    <BrowserRouter>
      <Boot />
      <OverlayHost />
    </BrowserRouter>
  </StrictMode>,
);
