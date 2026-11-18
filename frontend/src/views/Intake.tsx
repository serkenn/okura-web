// 書類（受信箱）・写真と入力の分割画面・確認待ち（提案）
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { post, ApiError } from '../lib/api';
import { QUICK, RecordForm, fieldsForRecord, fieldsForLedger, recordSummary, recordDate, type FormHandle } from '../lib/forms';
import { originLabel, enumLabel, conceptLabel } from '../lib/labels.js';
import { refreshStatus } from '../lib/status';
import { S, useS, loadMeta, loadRecords, personName, kindMeta, kindTitle, formCtx } from '../lib/store';
import { useApi } from '../lib/useApi';
import { Icon } from '../ui/Icon';
import { Avatar, ErrorNote, ProblemsList, Skeleton } from '../ui/bits';
import { toast, errorToast, modal, openDrawer } from '../ui/overlay';

const TABS: Array<[string, string]> = [['new', '未登録'], ['pending', '確認待ち'], ['done', '登録済み'], ['ignored', '対象外'], ['all', 'すべて']];
const enc = encodeURIComponent;

function evStatus(e: any): string {
  if (e.ignored) return 'ignored';
  if (e.records.length) return 'done';
  if (e.pending) return 'pending';
  return 'new';
}

function StatusChip({ e }: { e: any }) {
  const s = evStatus(e);
  if (s === 'new') return <span className="chip warn">未登録</span>;
  if (s === 'pending') return <span className="chip unverified">確認待ち</span>;
  if (s === 'done') return <span className="chip ok">登録済み</span>;
  return <span className="chip oos">対象外</span>;
}

function ThumbSm({ e }: { e: any }) {
  const isImg = e.mime.startsWith('image/') && e.mime !== 'image/heic';
  return <span className="thumb-sm">{isImg ? <img src={`/api/evidence/${e.id}/file`} alt="" loading="lazy" /> : e.ext.toUpperCase()}</span>;
}

function docName(e: any): string {
  const q = QUICK.find((x: any) => x.id === e.doc_type);
  return q ? q.name : (e.label || '未分類');
}

/** 語彙（記録の種類）と記録を取り直してから中身を出す（古い画面の loadMeta → loadRecords(true)）。key が変わるたびに取り直す */
function useFreshRecords(key: string) {
  const meta = useS((s) => s.meta);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<any>(null);
  useEffect(() => {
    let alive = true;
    Promise.all([loadMeta(), loadRecords(true)]).then(
      () => { if (alive) { setError(null); setDone(key); } },
      (e) => { if (alive) setError(e); });
    return () => { alive = false; };
  }, [key]);
  return { ready: !!meta && done === key, error };
}

// ------------------------------------------------------------------ 書類
export function UploadPage() {
  const { owner } = useParams();
  const q = useApi('/api/evidence');
  if (!q.data) return q.error ? <ErrorNote error={q.error} /> : <Skeleton />;
  return <UploadView key={owner || ''} ev={q.data} ownerArg={owner} />;
}

function UploadView({ ev, ownerArg }: { ev: any; ownerArg?: string }) {
  const navigate = useNavigate();
  const persons = useS((s) => s.persons);
  const [owner, setOwner] = useState<string>(() => ownerArg || S.me.person_id);
  const [docType, setDocType] = useState('');
  const [progress, setProgress] = useState('');
  const [over, setOver] = useState(false);
  const [tab, setTab] = useState<string>(() => (ev.evidence.some((e: any) => evStatus(e) === 'new') ? 'new' : 'all'));
  const fileIn = useRef<HTMLInputElement>(null);
  // アップロードの途中で選び直しても、そのときの値を使う（古い画面は欄の値をその都度読んでいた）
  const sel = useRef({ owner, docType });
  sel.current = { owner, docType };

  async function upload(files: File[]) {
    const ids: string[] = [];
    let i = 0;
    for (const f of files) {
      i++;
      setProgress(`アップロード中 ${i}/${files.length}…`);
      try {
        const buf = await f.arrayBuffer();
        const r = await post(`/api/evidence?owner=${enc(sel.current.owner)}`, undefined, { raw: buf, contentType: f.type || 'application/octet-stream' });
        if (r.duplicate) toast('同じ書類はアップロード済みです');
        if (sel.current.docType) await post(`/api/evidence/${r.id}/meta`, { doc_type: sel.current.docType });
        ids.push(r.id);
      } catch (e) { errorToast(e); }
    }
    setProgress('');
    if (ids.length) {
      toast(`${ids.length}件アップロードしました`);
      await refreshStatus();
      if (ids.length === 1) navigate(`/evidence/${ids[0]}`);
      else setTab('new'); // 一覧は書き込みのあとに自動で取り直される
    }
  }
  const uploadRef = useRef(upload);
  uploadRef.current = upload;

  // 貼り付け（クリップボードの画像）。この画面を開いているあいだだけ
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const files = [...(e.clipboardData?.files || [])];
      if (files.length) { e.preventDefault(); uploadRef.current(files); }
    };
    document.addEventListener('paste', onPaste);
    return () => document.removeEventListener('paste', onPaste);
  }, []);

  const list = ev.evidence.filter((e: any) => tab === 'all' || evStatus(e) === tab);
  return (
    <>
      <div className="page-head"><div className="grow"><h1>書類</h1>
        <p className="lead">給与明細・源泉徴収票・領収書</p></div></div>
      <div className="toolbar"><Icon name="users" size={16} cls="muted" />
        <select className="in" style={{ width: '180px' }} value={owner} onChange={(e) => setOwner(e.target.value)}>
          {persons.map((p) => <option key={p.person_id} value={p.person_id}>{p.display_name}</option>)}
        </select>
        <select className="in" style={{ width: '220px' }} value={docType} onChange={(e) => setDocType(e.target.value)}>
          <option value="">種類：あとで</option>
          {QUICK.map((q: any) => <option key={q.id} value={q.id}>{q.name}</option>)}
        </select>
      </div>
      <div className={`dropbar${over ? ' over' : ''}`} tabIndex={0} role="button" aria-label="書類を選ぶ"
        onClick={() => fileIn.current?.click()}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') fileIn.current?.click(); }}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); upload([...e.dataTransfer.files]); }}>
        <div className="d-ico"><Icon name="upload" size={20} /></div>
        <div className="grow"><b>ここにドラッグ＆ドロップ</b>
          <span className="muted" style={{ fontSize: '12.5px' }}>写真・PDF</span></div>
        <span className="muted">{progress}</span>
        <span className="btn primary"><Icon name="camera" size={15} />撮影・アップロード</span>
      </div>
      <input type="file" multiple accept="image/*,application/pdf" style={{ display: 'none' }} ref={fileIn}
        onChange={(e) => upload([...(e.currentTarget.files || [])])} />
      <div className="toolbar" style={{ marginTop: '24px' }}>
        <div className="seg">
          {TABS.map(([k, label]) => {
            const n = k === 'all' ? ev.evidence.length : ev.evidence.filter((e: any) => evStatus(e) === k).length;
            return <button type="button" key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{label}<span className="count">{String(n)}</span></button>;
          })}
        </div>
      </div>
      <div>
        {list.length ? (
          <div className="table-wrap"><table className="t">
            <thead><tr><th>書類</th><th>人</th><th>状態</th><th className="hide-sm">記録</th><th className="hide-sm">追加日</th><th className="hide-sm" /></tr></thead>
            <tbody>
              {list.map((e: any) => (
                <tr key={e.id} className="click" onClick={() => navigate(`/evidence/${e.id}`)}>
                  <td><div className="row" style={{ flexWrap: 'nowrap', gap: '12px' }}><ThumbSm e={e} /><div><div className="cell-main">{docName(e)}</div><div className="cell-sub mono">{`${e.ext.toUpperCase()}・${(e.size / 1024).toFixed(0)} KB`}</div></div></div></td>
                  <td><div className="row" style={{ flexWrap: 'nowrap' }}><Avatar id={e.owner_person} name={personName(e.owner_person)} small />{personName(e.owner_person)}</div></td>
                  <td><StatusChip e={e} /></td>
                  <td className="muted hide-sm">{e.records.length ? `${e.records.length} 件` : '—'}</td>
                  <td className="muted hide-sm">{(e.uploaded_at || '').slice(0, 10)}</td>
                  <td className="num hide-sm"><Icon name="chevronRight" size={16} cls="muted" /></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        ) : <div className="card empty"><Icon name="inbox" size={28} /><b>{tab === 'new' ? '未登録の書類はありません' : '書類はありません'}</b></div>}
      </div>
    </>
  );
}

// ------------------------------------------------------------------ 分割画面
type Cur = { q: any; proposal: any; km: any; initial: any; ai: Set<string>; n: number };

/** 入力欄の中身を作る（種類のボタン q か、確認待ちの提案 proposal から）。種類が使えなければ null */
function makeCur(e: any, q: any, proposal: any, n: number): Cur | null {
  const km = kindMeta(q ? q.kind : proposal.payload.record.kind);
  if (!km) return null;
  const rec = proposal ? proposal.payload.record : {};
  const initial = JSON.parse(JSON.stringify(rec));
  if (!proposal && q) {
    initial.roles = initial.roles || {};
    if (q.roleDefault) initial.roles[q.roleDefault] = e.owner_person;
    if (q.kind === 'medical_payment') initial.roles.patient = initial.roles.patient || e.owner_person;
    if (q.defaults) for (const [k, v] of Object.entries<any>(q.defaults)) initial[k] = { ...(initial[k] || {}), ...v };
  }
  const ai = new Set<string>();
  if (proposal && (proposal.origin === 'ai-ocr' || proposal.origin.startsWith('mcp:') || proposal.origin.startsWith('api:') || proposal.origin === 'inapp-agent')) {
    const walk = (o: any, p: string) => { for (const [k, v] of Object.entries<any>(o || {})) { const path = p ? `${p}.${k}` : k; if (v && typeof v === 'object' && !Array.isArray(v)) walk(v, path); else ai.add(path); } };
    walk(rec, '');
  }
  return { q, proposal, km, initial, ai, n };
}

/** 開いたときに出す入力欄：確認待ちがあればその提案、なければ書類の種類 */
function firstForm(e: any, mine: any[]): { q: any; proposal: any } | null {
  if (mine.length) return { q: QUICK.find((q: any) => q.kind === mine[0].payload.record.kind) || null, proposal: mine[0] };
  if (e.doc_type) { const q = QUICK.find((x: any) => x.id === e.doc_type); if (q) return { q, proposal: null }; }
  return null;
}

export function EvidencePage() {
  const { eid = '' } = useParams();
  const qe = useApi(`/api/evidence/${enc(eid)}`);
  const qp = useApi('/api/proposals');
  const qa = useApi('/api/evidence');
  const fresh = useFreshRecords(eid);
  // 登録・一時保存・却下・読み取りのあと：取り直してから、画面を最初の状態に戻す（古い画面の描き直し）
  const [round, setRound] = useState(0);
  const reset = async () => {
    await Promise.all([qe.reload(), qp.reload(), qa.reload(), loadRecords(true).catch(() => {})]);
    setRound((r) => r + 1);
  };
  const error = qe.error || qp.error || qa.error || fresh.error;
  if (!qe.data || !qp.data || !qa.data || !fresh.ready) return error ? <ErrorNote error={error} /> : <Skeleton />;
  const mine = qp.data.proposals.filter((p: any) => p.evidence_id === eid);
  return <EvidenceView key={`${eid}:${round}`} eid={eid} e={qe.data} mine={mine} all={qa.data} reset={reset} />;
}

function EvidenceView({ eid, e, mine, all, reset }: { eid: string; e: any; mine: any[]; all: any; reset: () => Promise<void> }) {
  const navigate = useNavigate();
  const persons = useS((s) => s.persons);
  const [zoom, setZoom] = useState(1);
  const [rot, setRot] = useState(0);
  const [owner, setOwner] = useState<string>(e.owner_person);
  const [onKind, setOnKind] = useState<string>(e.doc_type || '');
  const [cur, setCur] = useState<Cur | null>(() => { const f = firstForm(e, mine); return f ? makeCur(e, f.q, f.proposal, 0) : null; });
  const [err, setErr] = useState<any>(null);
  const form = useRef<FormHandle>(null);
  const seq = useRef(0);
  const warned = useRef(false);
  useEffect(() => {
    if (warned.current) return;
    warned.current = true;
    if (firstForm(e, mine) && !cur) toast('この種類は使えません', 'bad');
    // 開いたときに1度だけ
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const fileUrl = `/api/evidence/${enc(eid)}/file`;
  const isImg = e.mime.startsWith('image/') && e.mime !== 'image/heic';
  const idx = all.evidence.findIndex((x: any) => x.id === eid);
  const nextNew = all.evidence.find((x: any) => x.id !== eid && !x.records.length && !x.ignored);
  const prev = idx > 0 ? all.evidence[idx - 1] : null;
  const next = idx >= 0 && idx < all.evidence.length - 1 ? all.evidence[idx + 1] : null;

  function openForm(q: any, proposal: any) {
    const c = makeCur(e, q, proposal, ++seq.current);
    if (!c) { toast('この種類は使えません', 'bad'); return; }
    setErr(null);
    setCur(c);
  }

  async function register() {
    if (!cur || !form.current) return;
    const { proposal } = cur;
    const n = form.current.unverified();
    if (n) { toast(`未チェックの欄が${n}つあります`, 'bad'); return; }
    const { value, errors } = form.current.read();
    if (errors.length) { toast('入力エラーがあります', 'bad'); return; }
    const km = kindMeta(value.kind || (cur.q ? cur.q.kind : proposal.payload.record.kind));
    value.kind = km.kind;
    setErr(null);
    try {
      if (proposal) await post(`/api/proposals/${proposal.id}/accept`, { record: value });
      else await post('/api/records', { section: km.section, record: value, evidence_ids: [eid] });
      toast('登録しました');
      await refreshStatus();
      const again = await modal('登録しました', <p className="muted">同じ書類から続けて登録できます</p>, [
        { label: '続けて登録', value: 'again' }, nextNew ? { label: '次の書類へ', value: 'next', kind: 'primary' } : { label: '一覧に戻る', value: 'list', kind: 'primary' }]);
      if (again === 'next') navigate(`/evidence/${nextNew.id}`);
      else if (again === 'list') navigate('/upload');
      else await reset();
    } catch (e2) {
      errorToast(e2);
      if (e2 instanceof ApiError) setErr(e2);
    }
  }

  async function saveDraft() {
    if (!cur || !form.current) return;
    const { value } = form.current.read();
    const km = kindMeta(cur.q ? cur.q.kind : cur.proposal.payload.record.kind);
    value.kind = km.kind;
    try {
      if (cur.proposal) { toast('一時保存しました'); return; }
      await post('/api/proposals', { kind: 'record', section: km.section, record: value, evidence_id: eid, rationale: '下書き' });
      toast('一時保存しました');
      await refreshStatus();
      await reset();
    } catch (e2) { errorToast(e2); }
  }

  async function rejectProposal() {
    if (!cur || !cur.proposal) return;
    try { await post(`/api/proposals/${cur.proposal.id}/reject`, { note: '読み取りを捨てた' }); toast('却下しました'); await refreshStatus(); await reset(); }
    catch (e2) { errorToast(e2); }
  }

  async function aiRead(ack = false) {
    try {
      toast('読み取り中…');
      const r = await post(`/api/evidence/${enc(eid)}/extract`, ack ? { acknowledge_external: true } : {});
      if (!r.proposal_id) { toast('読み取れませんでした', 'bad'); return; }
      toast('読み取りました。金額を確認してください');
      await refreshStatus();
      await reset();
    } catch (e2) {
      if (e2 instanceof ApiError && e2.code === 'ack_required') {
        const ok = await modal('写真を外部の AI に送信しますか？', <p className="muted">送信先のサービスにデータが残ることがあります</p>, [{ label: 'キャンセル', value: false }, { label: '送信', value: true, kind: 'primary' }]);
        if (ok) aiRead(true);
      } else errorToast(e2);
    }
  }

  async function toggleIgnored() {
    const was = e.ignored;
    try {
      await post(`/api/evidence/${enc(eid)}/meta`, { ignored: !was });
      toast(was ? '戻しました' : '対象外にしました');
      await refreshStatus();
      await reset();
    } catch (e2) { errorToast(e2); }
  }

  async function changeOwner(v: string) {
    setOwner(v);
    try { await post(`/api/evidence/${enc(eid)}/owner`, { owner: v }); toast('変更しました'); } catch (e2) { errorToast(e2); }
  }

  async function chooseAnyKind() {
    const ref = { current: null as HTMLSelectElement | null };
    const kinds = S.meta.records.filter((k: any) => k.section === 'facts' || k.section === 'assets' || k.section === 'filed_documents');
    const kind = await modal<string>('種類を選択',
      <select className="in" ref={(el) => { ref.current = el; }}>{kinds.map((k: any) => <option key={k.kind} value={k.kind}>{k.title}</option>)}</select>,
      [{ label: 'キャンセル', value: null as any }, { label: '選択', kind: 'primary', run: () => (ref.current ? ref.current.value : '') }]);
    if (kind) openForm({ kind, name: kindTitle(kind), icon: 'layers', main: null }, null);
  }

  async function chooseKind(q: any) {
    setOnKind(q.id);
    openForm(q, null);
    try { await post(`/api/evidence/${enc(eid)}/meta`, { doc_type: q.id }); } catch { /* 表示の分類だけ */ }
  }

  return (
    <>
      <div className="toolbar">
        <Link className="btn ghost small" to="/upload"><Icon name="chevronLeft" size={14} />書類</Link>
        <div className="grow" />
        <button type="button" className="btn small" onClick={() => aiRead(false)}><Icon name="sparkles" size={14} />AI読み取り</button>
        <button type="button" className="btn small" onClick={toggleIgnored}>{e.ignored ? '対象外を解除' : '対象外にする'}</button>
        <button type="button" className="btn small icon" disabled={!prev} title="前の書類" onClick={() => prev && navigate(`/evidence/${prev.id}`)}><Icon name="chevronLeft" size={15} /></button>
        <button type="button" className="btn small icon" disabled={!next} title="次の書類" onClick={() => next && navigate(`/evidence/${next.id}`)}><Icon name="chevronRight" size={15} /></button>
      </div>
      <div className="split">
        <div className="pane-left">
          <div className="viewer-bar">
            <button type="button" className="btn small icon" title="拡大" onClick={() => setZoom((z) => Math.min(4, z * 1.25))}><Icon name="zoomIn" size={15} /></button>
            <button type="button" className="btn small icon" title="縮小" onClick={() => setZoom((z) => Math.max(0.3, z / 1.25))}><Icon name="zoomOut" size={15} /></button>
            <button type="button" className="btn small icon" title="回転" onClick={() => setRot((r) => (r + 90) % 360)}><Icon name="rotate" size={15} /></button>
            <div style={{ flex: 1 }} />
            <a className="btn small" href={fileUrl} target="_blank" rel="noopener"><Icon name="external" size={14} />別のタブ</a>
          </div>
          <div className="viewer">
            {isImg ? <img src={fileUrl} alt="書類の画像" style={zoom !== 1 || rot !== 0 ? { transform: `scale(${zoom}) rotate(${rot}deg)` } : undefined} />
              : e.mime === 'application/pdf' ? <iframe src={fileUrl} title="PDF" />
                : <div style={{ color: '#e7e5e4', padding: '2rem' }}>このファイルは表示できません</div>}
          </div>
        </div>
        <div className="pane-right">
          <div className="pane-body">
            <div className="row between">
              <div className="row"><StatusChip e={e} />{e.intact ? <span className="chip ok" title={`sha256 ${e.sha256}`}><Icon name="shield" size={12} />原本</span> : <span className="chip bad">原本が変更されています</span>}</div>
              <div className="row"><Icon name="users" size={15} cls="muted" />
                <select className="in" style={{ width: 'auto', height: '30px' }} value={owner} onChange={(ev) => changeOwner(ev.target.value)}>
                  {persons.map((p) => <option key={p.person_id} value={p.person_id}>{p.display_name}</option>)}
                </select></div>
            </div>
            {e.records.length ? <div className="note ok" style={{ marginTop: '12px' }}><Icon name="checkCircle" size={16} /><div>登録済み：{e.records.map((rid: string) => <Link key={rid} to={`/records/${enc(rid)}`} style={{ marginRight: '8px' }}>{rid}</Link>)}</div></div> : null}
            {mine.length ? <div className="note warn" style={{ marginTop: '12px' }}><Icon name="eye" size={16} />{`確認待ち ${mine.length}件`}</div> : null}
            <div className="section-title">種類</div>
            <div className="kinds" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))' }}>
              {QUICK.map((q: any) => (
                <button type="button" key={q.id} className={`kind-btn ${onKind === q.id ? 'on' : ''}`} onClick={() => chooseKind(q)}>
                  <span className="k-ico"><Icon name={q.icon} size={16} /></span><span className="k-name">{q.name}</span><span className="k-sub">{q.sub}</span>
                </button>
              ))}
              <button type="button" className="kind-btn" onClick={chooseAnyKind}><span className="k-ico"><Icon name="layers" size={16} /></span><span className="k-name">その他</span></button>
            </div>
            <div>
              {cur ? (
                <>
                  <div className="row" style={{ margin: '20px 0 4px' }}><h3 style={{ margin: 0, flex: 1 }}>{cur.q ? cur.q.name : cur.km.title}</h3>
                    {cur.proposal ? <span className="chip unverified">{`${originLabel(cur.proposal.origin)}・確認待ち`}</span> : null}</div>
                  {cur.ai.size ? <div className="note warn" style={{ marginBottom: '14px' }}><Icon name="eye" size={16} />黄色の欄は AI の読み取りです。写真と見比べてチェックしてください</div> : null}
                  <RecordForm key={cur.n} ref={form} fields={fieldsForRecord(cur.km)} initial={cur.initial} main={cur.q ? cur.q.main : null} ctx={formCtx()} ai={cur.ai} sync={cur.q ? cur.q.sync : null} />
                  <div>{err ? <div className="note bad" style={{ marginTop: '12px' }}><Icon name="alert" size={16} /><div>{err.message}<ProblemsList detail={err.detail} /></div></div> : null}</div>
                </>
              ) : null}
            </div>
          </div>
          <div className="pane-foot">
            {cur ? (
              <>
                <button type="button" className="btn primary" onClick={register}><Icon name="check" size={15} />登録</button>
                <button type="button" className="btn" onClick={saveDraft}>一時保存</button>
                <div style={{ flex: 1 }} />
                {cur.proposal ? <button type="button" className="btn ghost danger" onClick={rejectProposal}>却下</button> : null}
              </>
            ) : <span className="muted" style={{ fontSize: '12.5px' }}>種類を選んでください</span>}
          </div>
        </div>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ 確認待ち
function PerCandidateTable({ c }: { c: any }) {
  if (!c || !c.per_candidate || !c.per_candidate.length) return null;
  const cands: any[] = c.candidates || [];
  return (
    <div className="table-wrap" style={{ marginTop: '8px' }}><table className="t">
      <thead><tr><th />{cands.map((x, i) => <th key={i}>{enumLabel(String(x)) === String(x) ? personName(x) || x : enumLabel(String(x))}</th>)}</tr></thead>
      <tbody>{c.per_candidate.map((a: any, i: number) => (
        <tr key={i}><td>{`${personName(a.person)}：${conceptLabel(a.concept)}`}</td>{cands.map((x, k) => <td key={k} className="num">{(a.per_candidate[String(x)] || ['—']).join(' / ')}</td>)}</tr>
      ))}</tbody>
    </table></div>
  );
}

const INBOX_TABS: Array<[string, string]> = [['pending', '確認待ち'], ['accepted', '登録済み'], ['rejected', '却下']];
const PROPOSAL_KIND: Record<string, string> = { record: '記録', judgment: '回答', choice: '回答', forecast: '見込み' };

/** 提案の確認（ドロワーの中身）。登録するのは人 */
function ProposalForm({ p, km, close }: { p: any; km: any; close: () => void }) {
  const rec = p.payload.record || {};
  const isLedger = ['judgments', 'choices'].includes(p.payload.section);
  const [fields] = useState<any[]>(() => (isLedger ? fieldsForLedger(km) : fieldsForRecord(km)));
  const [ai] = useState(() => new Set<string>(fields.map((f: any) => f.path)));
  const [initial] = useState(() => JSON.parse(JSON.stringify(rec))); // API から来た値は書き換えない（写し）
  const [note, setNote] = useState<string>(p.rationale || '');
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const form = useRef<FormHandle>(null);
  const accept = async () => {
    if (!form.current || busy) return;
    if (form.current.unverified()) { toast(`未チェックの欄が${form.current.unverified()}つあります`, 'bad'); return; }
    const { value, errors } = form.current.read();
    if (errors.length) { toast('入力エラーがあります', 'bad'); return; }
    value.kind = km.kind;
    if (km.mark) value.mark = km.mark;
    setBusy(true);
    try {
      await post(`/api/proposals/${p.id}/accept`, { record: value, basis_note: note || undefined });
      toast('登録しました');
      close();
      await refreshStatus(); // 一覧は書き込みのあとに自動で取り直される
    } catch (e) { setBusy(false); errorToast(e); if (e instanceof ApiError) setErr(e); }
  };
  return (
    <div className="stack">
      <div className="note warn">{isLedger ? 'AI の提案です。回答するのはあなたです' : 'AI の提案です。各欄をチェックしてください'}</div>
      <PerCandidateTable c={p.candidates} />
      <RecordForm ref={form} fields={fields} initial={initial} ctx={formCtx()} ai={ai} />
      {isLedger ? <div className="field"><label>メモ</label><input type="text" className="in" placeholder="メモ（任意）" value={note} onChange={(e) => setNote(e.target.value)} /></div> : null}
      <div>{err ? <div className="note bad">{err.message}<ProblemsList detail={err.detail} /></div> : null}</div>
      <div className="row"><button type="button" className="btn primary big" onClick={accept}>登録</button></div>
    </div>
  );
}

function openProposal(p: any) {
  const rec = p.payload.record || {};
  const km = kindMeta(rec.kind);
  if (!km) { toast('この種類は使えません', 'bad'); return; }
  openDrawer(km.title, (close) => <ProposalForm p={p} km={km} close={() => close()} />);
}

function ProposalCard({ p, st }: { p: any; st: string }) {
  const persons = useS((s) => s.persons);
  const rec = p.payload.record || {};
  const who = Object.values<any>(rec.roles || rec.subject || {}).filter((v) => typeof v === 'string' && persons.some((x) => x.person_id === v));
  const reject = async () => {
    try { await post(`/api/proposals/${p.id}/reject`, { note: '人が捨てた' }); toast('却下しました'); await refreshStatus(); } catch (e) { errorToast(e); }
  };
  return (
    <div className="card">
      <div className="row">
        <span className="chip unverified">{originLabel(p.origin)}</span>
        <span className="chip">{PROPOSAL_KIND[p.kind] || p.kind}</span>
        <b style={{ flex: 1 }}>{kindTitle(rec.kind)}</b>
        <span className="muted">{(p.created_at || '').slice(0, 16).replace('T', ' ')}</span>
      </div>
      <div className="muted" style={{ marginTop: '4px' }}>{who.map(personName).join('・')} {recordDate(rec)} {recordSummary(rec)}</div>
      {p.rationale ? <div className="muted" style={{ marginTop: '6px' }}>{p.rationale}</div> : null}
      <PerCandidateTable c={p.candidates} />
      {p.evidence_id ? <Link to={`/evidence/${p.evidence_id}`} className="btn small" style={{ marginTop: '8px' }}><Icon name="receipt" size={14} />書類を表示</Link> : null}
      {st === 'pending' ? (
        <div className="row" style={{ marginTop: '8px' }}>
          <button type="button" className="btn primary" onClick={() => openProposal(p)}>確認</button>
          <button type="button" className="btn danger" onClick={reject}>却下</button>
        </div>
      ) : (
        <div className="muted" style={{ marginTop: '6px' }}>{(p.decided_at || '').slice(0, 16).replace('T', ' ')}{p.result_record_id ? <Link to={`/records/${enc(p.result_record_id)}`} style={{ marginLeft: '8px' }}>記録を見る</Link> : null}</div>
      )}
    </div>
  );
}

export function InboxPage() {
  const [st, setSt] = useState('pending');
  const q = useApi(`/api/proposals?status=${st}`);
  const fresh = useFreshRecords('inbox');
  // タブを切り替えたとき、新しい一覧が来るまで前の一覧を（前のタブの形のまま）出しておく
  const [shown, setShown] = useState<{ st: string; r: any } | null>(null);
  if (q.data && (!shown || shown.r !== q.data || shown.st !== st)) setShown({ st, r: q.data });
  const error = q.error || fresh.error;
  return (
    <>
      <div className="page-head"><div className="grow"><h1>確認待ち</h1>
        <p className="lead">AI が読み取った内容・提案。登録するまで計算に入りません</p></div></div>
      <div className="tabs">{INBOX_TABS.map(([k, l]) => <button type="button" key={k} className={st === k ? 'on' : ''} onClick={() => setSt(k)}>{l}</button>)}</div>
      <div className="stack">
        {shown && fresh.ready ? (
          <>
            {shown.r.hidden ? <div className="note">{`非公開 ${shown.r.hidden}件`}</div> : null}
            {shown.r.proposals.length ? shown.r.proposals.map((p: any) => <ProposalCard key={p.id} p={p} st={shown.st} />)
              : <div className="empty">{shown.st === 'pending' ? '要確認はありません' : 'ありません'}</div>}
          </>
        ) : error ? <ErrorNote error={error} /> : <Skeleton />}
      </div>
    </>
  );
}
