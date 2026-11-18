// パスキー（WebAuthn）のブラウザ側。サーバーが作った options をそのまま使い、応答を JSON にして返す
import { post } from './api';

const b64uToBuf = (s) => {
  const b = atob(s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4));
  return Uint8Array.from(b, (c) => c.charCodeAt(0)).buffer;
};
const bufToB64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

// IP アドレス・localhost・http ではパスキーを使えない（RP ID がドメインである必要がある）
export function passkeyAvailable() {
  return !!window.PublicKeyCredential && location.protocol === 'https:' && !/^(\d+\.){3}\d+$|^localhost$|^\[/.test(location.hostname);
}

function creationOptions(o) {
  if (PublicKeyCredential.parseCreationOptionsFromJSON) return PublicKeyCredential.parseCreationOptionsFromJSON(o);
  return { ...o, challenge: b64uToBuf(o.challenge), user: { ...o.user, id: b64uToBuf(o.user.id) },
    excludeCredentials: (o.excludeCredentials || []).map((c) => ({ ...c, id: b64uToBuf(c.id) })) };
}

function requestOptions(o) {
  if (PublicKeyCredential.parseRequestOptionsFromJSON) return PublicKeyCredential.parseRequestOptionsFromJSON(o);
  return { ...o, challenge: b64uToBuf(o.challenge), allowCredentials: (o.allowCredentials || []).map((c) => ({ ...c, id: b64uToBuf(c.id) })) };
}

function toJSON(cred) {
  if (typeof cred.toJSON === 'function') return cred.toJSON();
  const r = cred.response;
  const out = { id: cred.id, rawId: bufToB64u(cred.rawId), type: cred.type, clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {}, response: {
    clientDataJSON: bufToB64u(r.clientDataJSON) } };
  if (r.attestationObject) { out.response.attestationObject = bufToB64u(r.attestationObject); out.response.transports = r.getTransports ? r.getTransports() : []; }
  if (r.authenticatorData) {
    out.response.authenticatorData = bufToB64u(r.authenticatorData);
    out.response.signature = bufToB64u(r.signature);
    out.response.userHandle = r.userHandle ? bufToB64u(r.userHandle) : null;
  }
  return out;
}

export async function registerPasskey(label) {
  const { challenge_id: cid, options } = await post('/api/passkeys/register/options', {});
  const cred = await navigator.credentials.create({ publicKey: creationOptions(options) });
  await post('/api/passkeys/register/verify', { challenge_id: cid, credential: toJSON(cred), label });
}

export async function loginWithPasskey() {
  const { challenge_id: cid, options } = await post('/api/passkeys/login/options', {});
  const cred = await navigator.credentials.get({ publicKey: requestOptions(options) });
  await post('/api/passkeys/login/verify', { challenge_id: cid, credential: toJSON(cred) });
}
