// 確定申告：世帯（人 × 段の表）→ 1人の申告（①書類と記録 → ②決めること → ③結果 → ④申告書）。docs/ia-model.md
import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { Link, useParams } from 'react-router';
import { get } from '../lib/api';
import { QUICK } from '../lib/forms';
import { yen, timeKey } from '../lib/format';
import { conceptLabel } from '../lib/labels.js';
import { recalc } from '../lib/status';
import { S, useS, useDigest, loadMeta, loadRecords, kindMeta } from '../lib/store';
import { useApi } from '../lib/useApi';
import { Icon } from '../ui/Icon';
import { Avatar, ErrorNote, Skeleton } from '../ui/bits';
import { openRecordForm } from './Data';
import { questionText, openValue } from './Results';

const STEPS: Array<[string, string]> = [['docs', '書類と記録'], ['decide', '決めること'], ['result', '結果'], ['forms', '申告書']];
const enc = encodeURIComponent;

// 今申告する年分：1〜3月は前の年、それ以外はその年（作成コーナーと同じ考え方）
function defaultYear(years: number[]): number {
  const d = new Date();
  const want = d.getMonth() < 3 ? d.getFullYear() - 1 : d.getFullYear();
  return years.includes(want) ? want : years[years.length - 1];
}

function recYear(r: any): number | null {
  const w = (r.record || r).when || {};
  if (w.tax_year) return Number(w.tax_year);
  const s = w.on || w.from_on || '';
  return s ? Number(s.slice(0, 4)) : null;
}

function wareki(y: number) { return `令和${y - 2018}年分`; }

function StepState({ n, done }: { n: number; done: boolean }) {
  if (done) return <span className="step-st ok"><Icon name="check" size={12} />済み</span>;
  if (n) return <span className="step-st todo">{`${n}`}</span>;
  return <span className="step-st none">—</span>;
}

function personData(d: any, pid: string, year: number, records: any[], proposals: any[]) {
  const recs = records.filter((r) => (r.persons || []).includes(pid) && recYear(r) === year);
  const pend = proposals.filter((p) => JSON.stringify(((p.payload || {}).record) || {}).includes(pid));
  const qs: any[] = d ? d.questions.filter((q: any) => (q.persons || []).includes(pid) && (!q.years || q.years.includes(year))) : [];
  const decide = qs.filter((q) => q.means === '判断');
  const facts = qs.filter((q) => q.means === '事実');
  const vals: any[] = d ? d.key_values.filter((v: any) => v.person === pid && timeKey(v.time) === `Y${year}`) : [];
  const undet = vals.filter((v) => (v.states || []).includes('未確定')).length;
  return { recs, pend, decide, facts, vals, undet };
}

/** 開閉を state で持つ <details>。onOpen は開いたとき */
function Details({ className, style, summary, onOpen, children }: { className?: string; style?: CSSProperties; summary: ReactNode; onOpen?: () => void; children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <details className={className} style={style} open={open} onToggle={(e) => { const o = e.currentTarget.open; setOpen(o); if (o && onOpen) onOpen(); }}>
      {summary}{children}
    </details>
  );
}

const recAmount = (r: any) => { const am = r.record.amounts || {}; return am.gross ?? am.amount ?? am.payment_amount; };

// ------------------------------------------------------------------ 世帯（人 × 段）
export function TaxPage() {
  const { year: yearArg, pid, step } = useParams();
  const d = useDigest();
  const meta = useS((s) => s.meta);
  const persons = useS((s) => s.persons);
  const records = useS((s) => s.records);
  const q = useApi('/api/proposals');
  // 記録は開くたびに取り直す。最初の1回は待ち、そのあと（年・人・段の切り替え）は前の値を出したまま裏で取り直す
  const [ready, setReady] = useState(false);
  const [fail, setFail] = useState<any>(null);
  useEffect(() => {
    let alive = true;
    Promise.all([loadMeta(), loadRecords(true)]).then(
      () => { if (alive) { setFail(null); setReady(true); } },
      (e) => { if (alive) setFail(e); });
    return () => { alive = false; };
  }, [yearArg, pid, step]);

  const years: number[] = d ? [...new Set<number>(d.times.filter((t: any) => t.time.tax_year).map((t: any) => t.time.tax_year))].sort() : [new Date().getFullYear()];
  const year = Number(yearArg) || defaultYear(years);
  const p = pid ? persons.find((x) => x.person_id === pid) : null;
  if (pid && !p) return <div className="card empty"><b>この人は見つかりません</b></div>;
  // 確認待ちが読めないときは、ないものとして進める
  const prs: any[] | null = q.data ? q.data.proposals : q.error ? [] : null;
  if (!ready || !meta || !records || !prs) return fail ? <ErrorNote error={fail} /> : <Skeleton />;
  if (pid && p) return <Return d={d} year={year} pid={pid} p={p} step={step || 'docs'} records={records} prs={prs} />;

  const cross: any[] = d ? d.questions.filter((qq: any) => qq.means === '判断' && (qq.persons || []).length > 1) : [];
  return (
    <>
      <div className="page-head"><h1>確定申告</h1></div>
      <div className="seg seg-wide">{years.map((y) => <Link key={y} className={y === year ? 'on' : ''} to={`/tax/${y}`}>{wareki(y)}</Link>)}</div>
      {!d ? <div className="note warn" style={{ margin: '12px 0' }}><Icon name="refresh" size={16} /><div className="grow">まだ計算していません</div><button type="button" className="btn small" onClick={recalc}>計算</button></div> : null}
      {cross.length ? <Link className="band" to="/questions" style={{ marginTop: '12px' }}><Icon name="users" size={17} /><span>{`家族にまたがる決めること ${cross.length}件`}</span><Icon name="chevronRight" size={15} /></Link> : null}
      <div className="tax-table">
        {persons.map((pp) => {
          const vis = !d || d.persons.includes(pp.person_id);
          const x = personData(d, pp.person_id, year, records, prs);
          return (
            <Link key={pp.person_id} className="tax-row" to={`/tax/${year}/${enc(pp.person_id)}`}>
              <div className="tr-who"><Avatar id={pp.person_id} name={pp.display_name} /><b>{pp.display_name}</b></div>
              {vis ? (
                <div className="tr-steps">
                  <span className="tr-step"><small>書類と記録</small>{x.pend.length ? <span className="step-st todo">{`確認 ${x.pend.length}`}</span> : <span className="step-st">{`${x.recs.length}件`}</span>}</span>
                  <span className="tr-step"><small>決めること</small><StepState n={x.decide.length + x.facts.length} done={!!d && !x.decide.length && !x.facts.length} /></span>
                  <span className="tr-step"><small>結果</small>{d ? (x.undet ? <span className="step-st undet">{`未確定 ${x.undet}`}</span> : <span className="step-st ok"><Icon name="check" size={12} />確定</span>) : <span className="step-st none">未計算</span>}</span>
                  <span className="tr-step"><small>申告書</small><Icon name="chevronRight" size={15} cls="muted" /></span>
                </div>
              ) : <div className="muted row"><Icon name="lock" size={14} />非公開</div>}
            </Link>
          );
        })}
      </div>
      {d && d.query_out_of_scope.length ? (
        <div className="note" style={{ marginBottom: '8px' }}><Icon name="info" size={16} />
          <div><b>まだ計算できない年：</b>{d.query_out_of_scope.map((o: any) => o.display || o.reason).join('・')}</div></div>
      ) : null}
      <p className="muted" style={{ fontSize: '12.5px' }}>提出は確定申告書等作成コーナーで行います</p>
    </>
  );
}

// ------------------------------------------------------------------ 1人の申告
function Return({ d, year, pid, p, step, records, prs }: { d: any; year: number; pid: string; p: any; step: string; records: any[]; prs: any[] }) {
  const x = personData(d, pid, year, records, prs);
  return (
    <>
      <Link className="back-link" to={`/tax/${year}`}><Icon name="chevronLeft" size={15} />{`確定申告 ${wareki(year)}`}</Link>
      <div className="person-hero"><Avatar id={pid} name={p.display_name} /><div><h1>{p.display_name}</h1><div className="muted">{wareki(year)}</div></div></div>
      <div className="step-bar">
        {STEPS.map(([k, label], i) => (
          <Link key={k} className={`step ${k === step ? 'on' : ''}`} to={`/tax/${year}/${enc(pid)}/${k}`}>
            <span className="n">{String(i + 1)}</span><span>{label}</span>
          </Link>
        ))}
      </div>
      <div>
        {step === 'docs' ? <DocsStep x={x} pid={pid} />
          : step === 'decide' ? <DecideStep x={x} d={d} />
            : step === 'result' ? <ResultStep key={`${pid}:${year}`} x={x} d={d} pid={pid} year={year} />
              : <FormsStep pid={pid} year={year} />}
      </div>
    </>
  );
}

// ① 書類と記録：話題ごとに 入力あり／確認してください／なし（作成コーナー・TurboTax の話題の一覧）
function DocsStep({ x, pid }: { x: any; pid: string }) {
  const topics = QUICK.filter((q: any) => kindMeta(q.kind));
  // 追加のあと：記録を取り直す（確認待ちは書き込みのあとに自動で取り直される）
  const redraw = () => { loadRecords(true).catch(() => {}); };
  return (
    <>
      <div className="topic-list">
        {topics.map((q: any) => {
          const km = kindMeta(q.kind);
          const rs: any[] = x.recs.filter((r: any) => r.record.kind === q.kind);
          const pend: any[] = x.pend.filter((pr: any) => ((pr.payload || {}).record || {}).kind === q.kind);
          const total = rs.reduce((a, r) => { const am = r.record.amounts || {}; return a + (am.gross ?? am.amount ?? am.payment_amount ?? 0); }, 0);
          const add = () => {
            const init: any = { roles: {} };
            if (q.roleDefault) init.roles[q.roleDefault] = pid;
            openRecordForm(km, init, redraw);
          };
          return (
            <div className="topic" key={q.id}>
              <span className="tp-ico"><Icon name={q.icon} size={18} /></span>
              <div className="tp-main"><b>{q.name}</b>
                {pend.length ? <span className="step-st todo">{`確認してください ${pend.length}`}</span>
                  : rs.length ? <span className="step-st ok">{`入力あり ${rs.length}件${total ? `・${yen(total)}` : ''}`}</span> : <span className="step-st none">なし</span>}
                {rs.length ? (
                  <Details className="tp-recs" summary={<summary>記録を見る</summary>}>
                    {rs.map((r, i) => {
                      const v = recAmount(r);
                      return <Link key={r.record.id || r.id || i} to={`/records/${enc(r.record.id || r.id || '')}`}>{(r.record.when || {}).on || (r.record.when || {}).from_on || ''}{'　'}{v != null ? yen(v) : ''}</Link>;
                    })}
                  </Details>
                ) : null}
              </div>
              <div className="tp-act">
                {pend.length ? <Link className="btn small primary" to="/inbox">確かめる</Link> : null}
                <button type="button" className="btn small" onClick={add}><Icon name="plus" size={14} />追加</button>
              </div>
            </div>
          );
        })}
      </div>
      <div className="row" style={{ gap: '8px', marginTop: '12px' }}><Link className="btn" to="/upload"><Icon name="camera" size={15} />書類を撮る</Link><Link className="btn ghost" to="/records">記録の一覧</Link></div>
    </>
  );
}

// ② 決めること：答えごとに何が変わるかは質問の画面で
function DecideStep({ x, d }: { x: any; d: any }) {
  const all: any[] = [...x.decide, ...x.facts];
  if (!all.length) return <div className="card empty"><Icon name="checkCircle" size={28} /><b>{d ? '決めることはありません' : 'まだ計算していません'}</b></div>;
  return (
    <div className="card flush">
      {all.map((q) => (
        <Link key={q.id} className="q-row" to={`/questions/q:${enc(q.id)}`}>
          <span className={`chip ${q.means === '判断' ? 'undet' : 'warn'}`}>{q.means === '判断' ? '決める' : '入力'}</span>
          <span className="grow">{questionText(q)}</span><Icon name="chevronRight" size={15} cls="muted" />
        </Link>
      ))}
    </div>
  );
}

// ③ 結果：主な値（押すと根拠・未確定の分かれ目）
function ResultStep({ x, d, pid, year }: { x: any; d: any; pid: string; year: number }) {
  // すべての項目：開いたときに1度だけ取る
  const [all, setAll] = useState<null | 'loading' | { values?: any[]; error?: string }>(null);
  const t = d ? d.times.find((tt: any) => tt.key === `Y${year}`) : null;
  const groups: Array<{ inst: string; vals: any[] }> = [];
  for (const inst of (t ? t.institutions : [])) {
    const vals = (d.key_concepts[inst] || []).map((c: string) => x.vals.find((v: any) => v.concept === c)).filter(Boolean);
    if (vals.length) groups.push({ inst, vals });
  }
  // 未対応（判定コアがまだ扱えない値と理由。消さずに見せる）
  const oos: any[] = d ? d.out_of_scope.map((g: any) => ({ ...g, n: g.values.filter((v: any) => v.person === pid && timeKey(v.time) === `Y${year}`).length })).filter((g: any) => g.n) : [];
  const loadAll = async () => {
    if (all !== null) return;
    setAll('loading');
    try {
      const r = await get(`/api/results/${S.latest.result.hash}/values?person=${enc(pid)}&time=Y${year}`);
      setAll({ values: r.values });
    } catch (err: any) { setAll({ error: err.message }); }
  };
  const summaryStyle: CSSProperties = { cursor: 'pointer', fontWeight: 700 };
  return (
    <>
      {groups.length ? (
        <div className="card pv-card">
          {groups.map((g) => (
            <div className="pv-group" key={g.inst}><div className="section-title">{g.inst}</div>
              {g.vals.map((v) => (
                <button type="button" key={v.id} className="pv-row" onClick={() => openValue(v.id)}><span>{conceptLabel(v.concept)}</span>
                  <span className="num">{v.display ?? ((v.states || []).includes('未確定') ? '未確定' : '—')}</span><Icon name="chevronRight" size={14} cls="muted" /></button>
              ))}
            </div>
          ))}
        </div>
      ) : <div className="card empty"><b>{d ? 'この年分の値はありません' : 'まだ計算していません'}</b></div>}
      {x.undet ? <div className="note" style={{ marginTop: '12px' }}><Icon name="info" size={16} /><div>{`未確定 ${x.undet}件。`}<Link to={`/tax/${year}/${enc(pid)}/decide`}>決めること</Link>に答えると決まります</div></div> : null}
      {oos.length ? (
        <Details className="card" style={{ marginTop: '12px' }} summary={<summary style={summaryStyle}>{`未対応（${oos.reduce((a2, g) => a2 + g.n, 0)}項目）`}</summary>}>
          {oos.map((g, i) => <div className="basis" key={i}><div><span className="chip oos">{g.category}</span>{` ${g.n}項目`}</div><div className="muted">{g.reason}</div></div>)}
        </Details>
      ) : null}
      {d ? (
        <Details className="card" style={{ marginTop: '12px' }} onOpen={loadAll} summary={<summary style={summaryStyle}>すべての項目</summary>}>
          <div>
            {all === 'loading' ? <span className="spinner" />
              : all && all.error !== undefined ? <div className="muted">{all.error}</div>
                : all && all.values ? (
                  <div className="pv-card">
                    {all.values.map((v: any) => (
                      <button type="button" key={v.id} className="pv-row" onClick={() => openValue(v.id)}>
                        <span>{conceptLabel(v.concept)}</span><span className="num">{v.display ?? ((v.states || []).includes('未確定') ? '未確定' : (v.states || []).includes('対象外') ? '未対応' : '—')}</span><Icon name="chevronRight" size={14} cls="muted" /></button>
                    ))}
                  </div>
                ) : null}
          </div>
        </Details>
      ) : null}
    </>
  );
}

// ④ 申告書：欄ごとの値は申告書の画面（コピー・写した印）
function FormsStep({ pid, year }: { pid: string; year: number }) {
  return (
    <div className="card"><p style={{ marginTop: 0 }}>作成コーナーに写す欄ごとの値です。</p>
      <div className="row" style={{ gap: '8px', flexWrap: 'wrap' }}>
        <Link className="btn primary" to={`/forms/${enc(pid)}/${year}`}><Icon name="file" size={15} />申告書の欄を開く</Link>
        <a className="btn" href="https://www.keisan.nta.go.jp/" target="_blank" rel="noopener noreferrer">作成コーナー<Icon name="external" size={14} /></a>
      </div>
    </div>
  );
}
