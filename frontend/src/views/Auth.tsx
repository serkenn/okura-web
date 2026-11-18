// ログインと最初の設定
import { useState, type FormEvent, type ReactNode } from 'react';
import { post } from '../lib/api';
import { TAGLINE } from '../lib/copy';
import { passkeyAvailable, loginWithPasskey } from '../lib/passkey.js';
import { Icon } from '../ui/Icon';
import { errorToast } from '../ui/overlay';

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <div className="field"><label>{label}</label>{children}{hint ? <div className="hint">{hint}</div> : null}</div>;
}

export function LoginPage() {
  const [login, setLogin] = useState('');
  const [pw, setPw] = useState('');
  const passkey = passkeyAvailable();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try { await post('/api/login', { login, password: pw }); location.reload(); }
    catch (err) { errorToast(err); }
  };
  return (
    <div className="auth-wrap">
      <div className="brand-big"><img src="/icon.svg" alt="" /><div><h1>okura-web</h1><div className="muted">{TAGLINE}</div></div></div>
      {passkey ? (
        <div className="card form">
          <button className="btn primary big" type="button" onClick={async () => {
            try { await loginWithPasskey(); location.reload(); }
            catch (err: any) { if (err && err.name === 'NotAllowedError') return; errorToast(err); }
          }}><Icon name="key" size={18} />パスキーでログイン</button>
        </div>
      ) : null}
      <form className="card form" onSubmit={submit}>
        <Field label="ログイン名"><input type="text" autoComplete="username" autoFocus={!passkey} value={login} onChange={(e) => setLogin(e.target.value)} /></Field>
        <Field label="パスワード"><input type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
        <button className={`btn ${passkey ? '' : 'primary'} big`} type="submit">ログイン</button>
      </form>
    </div>
  );
}

export function SetupPage() {
  const [f, setF] = useState({ household_name: 'わが家', display_name: '', birth_on: '', login: '', password: '' });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await post('/api/setup', f);
      location.href = '/settings/consents';
    } catch (err) { errorToast(err); }
  };
  return (
    <div className="auth-wrap">
      <div className="brand-big"><img src="/icon.svg" alt="" /><div><h1>okura-web をはじめる</h1><div className="muted">データはこのパソコンに保存されます</div></div></div>
      <form className="card form" onSubmit={submit} style={{ marginTop: '12px' }}>
        <Field label="家族の名前"><input type="text" value={f.household_name} onChange={set('household_name')} /></Field>
        <Field label="あなたの名前"><input type="text" placeholder="例：たろう" autoFocus value={f.display_name} onChange={set('display_name')} /></Field>
        <Field label="生年月日"><input type="date" value={f.birth_on} onChange={set('birth_on')} /></Field>
        <Field label="ログイン名"><input type="text" autoComplete="username" placeholder="英数字（例 taro）" value={f.login} onChange={set('login')} /></Field>
        <Field label="パスワード（10文字以上）"><input type="password" autoComplete="new-password" value={f.password} onChange={set('password')} /></Field>
        <button className="btn primary big" type="submit">はじめる</button>
      </form>
    </div>
  );
}
