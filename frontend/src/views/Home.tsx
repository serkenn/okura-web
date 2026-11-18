// ホーム：初回は「何のアプリか」と最初の一歩。2回目からは「やること」と「家族ごとの壁」
import { useState } from 'react';
import { Link } from 'react-router';
import { TAGLINE, WALL_NAMES } from '../lib/copy';
import { yen, ageOn, today } from '../lib/format';
import { conceptLabel } from '../lib/labels.js';
import { recalc } from '../lib/status';
import { useS, useDigest } from '../lib/store';
import { Icon } from '../ui/Icon';
import { Avatar } from '../ui/bits';
import { askText } from '../ui/overlay';

const WALLS = Object.keys(WALL_NAMES);
const FIGURES: Array<[string, string]> = [
  ['所得税.給与等の収入金額', '給与収入'],
  ['所得税.合計所得金額', '所得'],
  ['所得税.所得税及び復興特別所得税の額', '所得税'],
  ['所得税.還付される税額', '還付'],
];

/** 壁（境目）：いまの値と、判定コアが出した境目までの差をそのまま出す */
export function WallView({ b, hourly }: { b: any; hourly?: number | null }) {
  const cur = b.compared ? b.compared.current : null;
  const cross = b.crossing_value;
  const crit = b.criterion || {};
  const upper = b.kind === '上限';
  let pct = 0;
  if (typeof cur === 'number' && typeof cross === 'number' && cross > 0) pct = Math.max(0, Math.min(100, (cur / cross) * 100));
  const diff = b.difference;
  const crossed = upper ? diff <= 0 : diff > 0;
  const cls = crossed ? 'over' : pct > 85 ? 'near' : '';
  const hours = hourly && b.compared && /年間収入|収入金額/.test(b.compared.concept) && diff > 0 ? Math.ceil(diff / hourly) : null;
  const name = WALL_NAMES[b.concept] || conceptLabel(b.concept);
  return (
    <div className={`wall ${cls}`} title={`${b.compared ? conceptLabel(b.compared.concept) : ''} ${yen(cur)}／基準 ${yen(crit.value)}${crit.comparison || ''}`}>
      <div className="w-head"><span>{name}</span>{crossed ? <b style={{ color: 'var(--bad)' }}>超えています</b> : <span>あと <b>{yen(Math.abs(diff))}</b></span>}</div>
      <div className="bar" role="img" aria-label={`${pct.toFixed(0)}%`}><i style={{ width: `${pct}%` }} /></div>
      {hours ? <div className="w-left">{`時給換算 約${hours}時間`}</div> : null}
    </div>
  );
}

function FirstView() {
  return (
    <div className="welcome">
      <img src="/icon.svg" alt="" className="w-logo" />
      <h1>{TAGLINE}</h1>
      <ol className="w-steps">
        <li><span className="w-ico"><Icon name="camera" size={22} /></span><b>撮る</b><span>給与明細・領収書</span></li>
        <li><span className="w-ico"><Icon name="checkCircle" size={22} /></span><b>確認</b><span>読み取った金額</span></li>
        <li><span className="w-ico"><Icon name="chart" size={22} /></span><b>わかる</b><span>税金・扶養の壁</span></li>
      </ol>
      <div className="w-actions">
        <Link className="btn primary big" to="/upload"><Icon name="camera" size={18} />書類をアップロード</Link>
        <Link className="btn big" to="/family"><Icon name="users" size={18} />家族を追加</Link>
      </div>
    </div>
  );
}

function PersonCard({ p, d, ty }: { p: any; d: any; ty: any }) {
  const key = `okura.hourly.${p.person_id}`;
  const [hourly, setHourly] = useState<number | null>(() => Number(localStorage.getItem(key) || 0) || null);
  const age = ageOn(p.birth_on, today());
  const head = (
    <Link className="p-head" to={`/person/${encodeURIComponent(p.person_id)}`}>
      <Avatar id={p.person_id} name={p.display_name} />
      <div style={{ flex: 1, minWidth: 0 }}><b>{p.display_name}</b><div className="muted" style={{ fontSize: '12.5px' }}>{age !== null ? `${age}歳` : ''}</div></div>
      <Icon name="chevronRight" size={16} cls="muted" />
    </Link>
  );
  if (!d) return <div className="card person-card">{head}</div>;
  if (!d.persons.includes(p.person_id)) return <div className="card person-card">{head}<div className="muted row"><Icon name="lock" size={15} />非公開</div></div>;
  const walls = d.boundaries
    .filter((b: any) => b.person === p.person_id && WALLS.includes(b.concept) && (b.time.tax_year === (ty && ty.time.tax_year) || b.time.on))
    .sort((a: any, b: any) => Math.abs(a.difference) - Math.abs(b.difference)).slice(0, 2);
  const figs = FIGURES
    .map(([c, label]) => [label, d.key_values.find((v: any) => v.person === p.person_id && v.concept === c && ty && v.time.tax_year === ty.time.tax_year)] as [string, any])
    .filter(([, v]) => v && (v.display !== '0円' || v.undetermined));
  const askHourly = async () => {
    const v = await askText('時給を設定', '時給（円）を入れると、壁まで何時間かがわかります', { required: false, initial: String(hourly || '') });
    if (v === null) return;
    const n = parseInt(String(v).replace(/[^\d]/g, ''), 10);
    if (n > 0) { localStorage.setItem(key, String(n)); setHourly(n); } else { localStorage.removeItem(key); setHourly(null); }
  };
  return (
    <div className="card person-card">{head}
      {walls.map((b: any, i: number) => <WallView key={i} b={b} hourly={hourly} />)}
      {figs.length ? (
        <div className="figs">{figs.map(([label, v]) => (
          <div className="fig" key={label}><span>{label}</span>
            <b>{v.display ?? (v.undetermined ? <span className="chip undet">未確定</span> : <span className="chip oos" title={v.out_of_scope ? v.out_of_scope.reason : ''}>未対応</span>)}</b>
          </div>
        ))}</div>
      ) : null}
      <button type="button" className="link-btn" onClick={askHourly}><Icon name="wallet" size={14} />{hourly ? `時給 ${yen(hourly)}` : '時給を設定'}</button>
    </div>
  );
}

export default function Home() {
  const d = useDigest();
  const persons = useS((s) => s.persons);
  const latest = useS((s) => s.latest);
  const me = useS((s) => s.me);
  const household = useS((s) => s.household);
  const evidenceNew = useS((s) => s.evidenceNew);
  const proposals = useS((s) => s.proposals);
  const bookPending = useS((s) => s.bookPending);
  if (!d && persons.length <= 1 && !evidenceNew) return <FirstView />;

  const count = (means: string) => (d ? d.questions.filter((q: any) => q.means === means).length : 0);
  const qJudge = count('判断'), qFact = count('事実'), qInj = count('注入');
  const consentsMissing = me.consents_missing && me.consents_missing.length;
  const todos = ([
    evidenceNew ? ['camera', '書類を登録', evidenceNew, '/upload'] : null,
    proposals ? ['inbox', '確認待ちの記録', proposals, '/inbox'] : null,
    bookPending ? ['list', '登録待ちの入出金', bookPending, '/txns/pending'] : null,
    qJudge ? ['question', '決めること', qJudge, '/questions'] : null,
    qFact ? ['home', '住所・保険を入力', qFact, `/questions/${encodeURIComponent('事実')}`] : null,
    persons.length <= 1 ? ['users', '家族を追加', 0, '/family'] : null,
    consentsMissing ? ['lock', '共有設定', 0, '/settings/consents'] : null,
    qInj ? ['building', '市区町村・保険の設定', qInj, '/settings/injections'] : null,
  ] as Array<[string, string, number, string] | null>).filter((t): t is [string, string, number, string] => !!t);

  const ty = d ? (d.times.find((t: any) => t.key === `Y${new Date().getFullYear()}`) || d.times.filter((t: any) => t.key.startsWith('Y')).slice(-1)[0]) : null;
  const stale = latest && latest.result && latest.result.stale;
  return (
    <>
      <div className="page-head keep"><div className="grow"><h1>{ty ? `${ty.time.tax_year}年` : 'ホーム'}</h1></div>
        <Link className="btn primary hide-sm" to="/upload"><Icon name="camera" size={15} />書類をアップロード</Link></div>
      {stale ? <div className="note warn" style={{ marginBottom: '14px' }}><Icon name="refresh" size={16} /><div style={{ flex: 1 }}>記録が変わりました</div><button type="button" className="btn small" onClick={recalc}>再計算</button></div> : null}
      {household.ir_error ? <div className="note bad" style={{ marginBottom: '14px' }}><Icon name="alert" size={16} />{household.ir_error.message}</div> : null}
      <div className="grid main-side">
        <div>
          {todos.length ? (
            <div className="card flush">
              <div className="card-head"><h3>やること</h3></div>
              <ul className="checklist todo-list">
                {todos.map(([ico, title, n, href]) => (
                  <li key={href}><Link to={href}>
                    <span className="td-ico"><Icon name={ico} size={18} /></span>
                    <div className="t-body"><div className="t-title">{title}</div></div>
                    {n ? <span className="badge">{String(n)}</span> : null}
                    <Icon name="chevronRight" size={16} cls="muted" />
                  </Link></li>
                ))}
              </ul>
            </div>
          ) : <div className="card done-card"><Icon name="checkCircle" size={22} /><b>やることはありません</b></div>}
          <h2>家族</h2>
          <div className="grid c2">{persons.map((p) => <PersonCard key={p.person_id} p={p} d={d} ty={ty} />)}</div>
        </div>
        <div className="stack hide-sm">
          <Link className="upload-tile" to="/upload"><Icon name="camera" size={28} /><b>書類をアップロード</b><span>ドラッグ＆ドロップもできます</span></Link>
          <div className="card">
            <div className="row between"><b>計算</b>
              {latest && latest.running ? <span className="chip info">計算中</span> : stale ? <span className="chip warn">再計算が必要</span> : d ? <span className="chip ok">最新</span> : <span className="chip">未計算</span>}</div>
            {d ? <div className="muted" style={{ fontSize: '12.5px', marginTop: '6px' }}>{`${(latest.result.finished_at || '').slice(5, 16).replace('T', ' ').replace('-', '/')} 更新`}</div> : null}
            <button type="button" className="btn" style={{ marginTop: '12px', width: '100%' }} onClick={recalc}><Icon name="refresh" size={14} />再計算</button>
          </div>
        </div>
      </div>
      <Link className="fab" to="/upload" aria-label="書類をアップロード"><Icon name="camera" size={24} /></Link>
    </>
  );
}
