// 招待リンクで開いた人の画面：その人あての質問に、1問ずつ答えるだけ（金額は出さない）
import { useEffect, useState } from 'react';
import { get, post, setCsrf, ApiError } from '../lib/api';
import { setS } from '../lib/store';
import { Icon } from '../ui/Icon';
import { Skeleton } from '../ui/bits';
import { toast, errorToast } from '../ui/overlay';
import { questionText, candLabel } from './Results';

// リンク（/join/<秘密>）を使って、この端末をその人の端末として登録する。秘密は URL から消す
let joining: Promise<unknown> | null = null; // リンクは1回しか使えない（2回送らない）

export function JoinPage({ token }: { token: string }) {
  const [state, setState] = useState<'wait' | 'ok' | { error: string }>('wait');
  useEffect(() => {
    history.replaceState(null, '', '/');
    joining ??= post('/api/join', { token });
    joining.then(() => setState('ok'), (e) => setState({ error: e instanceof ApiError ? e.message : 'リンクを開けませんでした' }));
  }, [token]);
  if (state === 'wait') return <div className="guest"><Skeleton /></div>;
  if (state === 'ok') return <GuestPage />;
  return (
    <div className="guest"><div className="card empty"><Icon name="alert" size={28} />
      <b>{state.error}</b><p className="muted">送ってくれた人に、新しいリンクを頼んでください</p></div></div>
  );
}

export function GuestPage() {
  const [me, setMe] = useState<any>(null);
  const [idx, setIdx] = useState(0);
  const [choice, setChoice] = useState<any>(null);
  const [done, setDone] = useState<Set<string>>(() => new Set());
  const [note, setNote] = useState('');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    get('/api/guest/me').then((m) => { setCsrf(m.csrf); setS({ persons: m.persons }); setMe(m); }, errorToast);
  }, []);
  if (!me) return <div className="guest"><Skeleton /></div>;

  const qs: any[] = me.questions;
  const head = (
    <div className="guest-head"><img src="/icon.svg" alt="" />
      <div><b>{`${me.person.display_name}さんへの質問`}</b>{me.from ? <small className="muted">{`${me.from}さんから`}</small> : null}</div></div>
  );
  if (!qs.length || done.size === qs.length) {
    return (
      <div className="guest">{head}<div className="card empty"><Icon name="checkCircle" size={36} />
        <b>{qs.length ? 'ありがとうございました' : 'いま答える質問はありません'}</b>
        <p className="muted">{qs.length ? '答えは送った人に届きました。この画面は閉じてかまいません' : 'また質問が来たら、同じリンクで開けます'}</p></div></div>
    );
  }
  let i = idx;
  while (done.has(qs[i].id)) i = (i + 1) % qs.length;
  const q = qs[i];
  const next = () => { setDone(new Set([...done, q.id])); setChoice(null); setIdx(i); };
  const answer = async () => {
    setSending(true);
    try {
      await post('/api/guest/answer', { question_id: q.id, candidate: choice, note: note || undefined });
      toast('送りました');
      setNote('');
      next();
    } catch (e) { errorToast(e); } finally { setSending(false); }
  };
  return (
    <div className="guest">{head}
      <div className="q-eyebrow">{`${done.size + 1} / ${qs.length}`}</div>
      <h1 className="guest-q">{questionText(q)}</h1>
      {q.candidates.map((c: any, k: number) => (
        <button type="button" key={k} className={`choice ${choice === c ? 'on' : ''}`} onClick={() => setChoice(c)}>
          <span className="radio" /><div className="c-title">{candLabel(c)}</div>
        </button>
      ))}
      <div className="field" style={{ marginTop: '8px' }}><input type="text" className="in" placeholder="ひとこと（任意）" value={note} onChange={(e) => setNote(e.target.value)} /></div>
      <div className="guest-foot">
        <button type="button" className="btn ghost" onClick={next}>わからない</button>
        <button type="button" className="btn primary big" disabled={choice === null || sending} onClick={answer}>答える<Icon name="chevronRight" size={16} /></button>
      </div>
    </div>
  );
}
