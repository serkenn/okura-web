"""パスキー（WebAuthn）でログインする。検証は .work/venvs/auth の webauthn をサブプロセスで動かす（bridge/passkey.py）。

- 登録はログインしている人の画面だけ（エージェントのトークン・招待リンクの端末は不可）。
- RP ID と origin は、サーバーに設定した公開のホスト名（--public-host）からだけ作る。リクエストの Host がその一覧にないときは使えない。
  （パスキーは IP アドレス（127.0.0.1）・http の LAN では使えない。この PC ではパスワードでログインする）
- challenge はサーバーが作って保存し、1回だけ・5分で切れる。ユーザーの確認（指紋・顔・PIN）は必須。
- 資格情報は ID で引き、userHandle がそのアカウントのものかを確かめる。使ったら sign_count を保存する。
- 失敗の理由（例外の文）は画面にもログにも出さない。
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
import secrets
import threading
import time
from typing import Any

from . import api
from . import db as dbm
from .api import _audit, _human, router
from .server import HttpError, Request, Response, session_cookie

CHALLENGE_SECONDS = 300
MAX_CREDENTIAL_BYTES = 64 * 1024
_RATE: dict[str, list[float]] = {}
_RATE_LOCK = threading.Lock()


def _app():
    return api.APP


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _rp(req: Request) -> tuple[str, str]:
    """(RP ID, origin)。公開のホスト名のときだけ。"""
    host = (req.header("Host") or "").lower()
    public = getattr(req.handler.server, "public_hosts", set())
    if host not in public or ":" in host:
        raise HttpError(400, "パスキーは公開のアドレス（https）で使う", code="passkey_host")
    return host, f"https://{host}"


def _bridge(payload: dict[str, Any]) -> dict[str, Any]:
    app = _app()
    r = app.engine._run(app.cfg.auth_python, [str(app.cfg.bridge_dir / "passkey.py")], stdin=json.dumps(payload).encode("utf-8"), timeout=30)
    try:
        out = json.loads(r.stdout.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        out = {"ok": False, "error": "bridge"}
    return out


def _rate_ok(key: str, limit: int = 20, window: int = 600) -> bool:
    now = time.monotonic()
    with _RATE_LOCK:
        xs = [t for t in _RATE.get(key, []) if now - t < window]
        if len(xs) >= limit:
            _RATE[key] = xs
            return False
        xs.append(now)
        _RATE[key] = xs
        return True


def _new_challenge(kind: str, user_id: str | None = None, user_handle: str | None = None) -> tuple[str, str]:
    cid = dbm.new_id("pkc", 8)
    ch = _b64e(secrets.token_bytes(32))
    with _app().db.tx() as c:
        cutoff = (dbm.now() - _dt.timedelta(seconds=CHALLENGE_SECONDS * 4)).isoformat()
        c.execute("DELETE FROM passkey_challenges WHERE created_at < ?", (cutoff,))
        c.execute("INSERT INTO passkey_challenges(id, kind, challenge, user_id, user_handle, created_at) VALUES (?,?,?,?,?,?)",
                  (cid, kind, ch, user_id, user_handle, dbm.now_iso()))
    return cid, ch


def _take_challenge(cid: Any, kind: str) -> dict[str, Any]:
    """challenge を1回だけ取り出す（使った印を付ける）。"""
    if not isinstance(cid, str):
        raise HttpError(400, "やり直してください", code="passkey_challenge")
    with _app().db.tx() as c:
        row = c.execute("SELECT * FROM passkey_challenges WHERE id=? AND kind=?", (cid, kind)).fetchone()
        if row is None or row["used_at"]:
            raise HttpError(400, "やり直してください", code="passkey_challenge")
        c.execute("UPDATE passkey_challenges SET used_at=? WHERE id=?", (dbm.now_iso(), cid))
    created = _dt.datetime.fromisoformat(row["created_at"])
    if (dbm.now() - created).total_seconds() > CHALLENGE_SECONDS:
        raise HttpError(400, "時間切れです。やり直してください", code="passkey_challenge")
    return dict(row)


def _credential(b: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    cred = b.get("credential")
    if not isinstance(cred, dict):
        raise HttpError(400, "パスキーの応答の形が違う", code="passkey_shape")
    text = json.dumps(cred)
    if len(text) > MAX_CREDENTIAL_BYTES:
        raise HttpError(400, "パスキーの応答が大きすぎる", code="passkey_shape")
    return text, cred


# ---------------------------------------------------------------------------- 登録（ログインしている人）
def _human_session(req: Request) -> None:
    _human(req)
    if req.principal is None or req.principal.kind != "session":
        raise HttpError(403, "ログインしている人の画面で行う", code="human_only")


@router.route("POST", "/api/passkeys/register/options")
def register_options(req: Request) -> Any:
    _human_session(req)
    rp_id, _ = _rp(req)
    p = req.principal
    assert p is not None
    row = _app().db.one("SELECT user_handle FROM passkeys WHERE user_id=? LIMIT 1", (p.user_id,))
    handle = row["user_handle"] if row else _b64e(secrets.token_bytes(32))
    exclude = [r["id"] for r in _app().db.all("SELECT id FROM passkeys WHERE user_id=? AND revoked_at IS NULL", (p.user_id,))]
    cid, ch = _new_challenge("register", p.user_id, handle)
    out = _bridge({"op": "register_options", "rp_id": rp_id, "rp_name": "okura-web", "user_handle": handle,
                   "user_name": "okura-web", "challenge": ch, "exclude": exclude})
    if not out.get("ok"):
        raise HttpError(500, "パスキーの準備ができなかった", code="passkey_bridge")
    return {"challenge_id": cid, "options": out["options"]}


@router.route("POST", "/api/passkeys/register/verify")
def register_verify(req: Request) -> Any:
    _human_session(req)
    rp_id, origin = _rp(req)
    p = req.principal
    assert p is not None
    b = req.json()
    text, _ = _credential(b)
    ch = _take_challenge(b.get("challenge_id"), "register")
    if ch["user_id"] != p.user_id:
        raise HttpError(400, "やり直してください", code="passkey_challenge")
    out = _bridge({"op": "register_verify", "credential": text, "challenge": ch["challenge"], "origin": origin, "rp_id": rp_id})
    if not out.get("ok"):
        raise HttpError(400, "パスキーを確かめられなかった", code="passkey_invalid")
    label = str(b.get("label") or "").strip()[:40] or "パスキー"
    with _app().db.tx() as c:
        if c.execute("SELECT 1 FROM passkeys WHERE id=?", (out["credential_id"],)).fetchone():
            raise HttpError(400, "このパスキーはもう登録してある", code="passkey_dup")
        c.execute("INSERT INTO passkeys(id, user_id, user_handle, public_key, sign_count, label, created_at) VALUES (?,?,?,?,?,?,?)",
                  (out["credential_id"], p.user_id, ch["user_handle"], out["public_key"], int(out["sign_count"]), label, dbm.now_iso()))
    _audit(req, "passkey_registered", None)
    return {"ok": True}


@router.route("GET", "/api/passkeys")
def list_passkeys(req: Request) -> Any:
    _human_session(req)
    p = req.principal
    assert p is not None
    rows = _app().db.all("SELECT id, label, created_at, last_used_at FROM passkeys WHERE user_id=? AND revoked_at IS NULL ORDER BY created_at", (p.user_id,))
    public = getattr(req.handler.server, "public_hosts", set())
    host = (req.header("Host") or "").lower()
    return {"passkeys": [{"id": r["id"][:12], "label": r["label"], "created_at": r["created_at"], "last_used_at": r["last_used_at"]} for r in rows],
            "available": host in public}


@router.route("POST", "/api/passkeys/{pid}/revoke")
def revoke_passkey(req: Request) -> Any:
    _human_session(req)
    p = req.principal
    assert p is not None
    pid = req.params["pid"]
    with _app().db.tx() as c:
        n = c.execute("UPDATE passkeys SET revoked_at=? WHERE user_id=? AND substr(id, 1, 12)=? AND revoked_at IS NULL",
                      (dbm.now_iso(), p.user_id, pid)).rowcount
    if not n:
        raise HttpError(404, "パスキーがない", code="not_found")
    _audit(req, "passkey_revoked", None)
    return {"ok": True}


# ---------------------------------------------------------------------------- ログイン
@router.route("POST", "/api/passkeys/login/options", public=True, no_csrf=True)
def login_options(req: Request) -> Any:
    rp_id, _ = _rp(req)
    if not _rate_ok(f"opt:{req.handler.client_address[0]}", limit=60):
        raise HttpError(429, "少し待ってから", code="rate")
    cid, ch = _new_challenge("login")
    out = _bridge({"op": "login_options", "rp_id": rp_id, "challenge": ch})
    if not out.get("ok"):
        raise HttpError(500, "パスキーの準備ができなかった", code="passkey_bridge")
    return {"challenge_id": cid, "options": out["options"]}


@router.route("POST", "/api/passkeys/login/verify", public=True, no_csrf=True)
def login_verify(req: Request) -> Any:
    rp_id, origin = _rp(req)
    if not _rate_ok(f"login:{req.handler.client_address[0]}"):
        raise HttpError(429, "少し待ってから", code="rate")
    b = req.json()
    text, cred = _credential(b)
    ch = _take_challenge(b.get("challenge_id"), "login")
    raw_id = cred.get("rawId") or cred.get("id")
    handle = ((cred.get("response") or {}).get("userHandle")) if isinstance(cred.get("response"), dict) else None
    row = _app().db.one("SELECT p.*, u.disabled FROM passkeys p JOIN users u ON u.id=p.user_id WHERE p.id=? AND p.revoked_at IS NULL",
                        (raw_id if isinstance(raw_id, str) else "",))
    if row is None or row["disabled"] or not isinstance(handle, str) or handle.rstrip("=") != row["user_handle"]:
        raise HttpError(401, "このパスキーではログインできない", code="passkey_unknown")
    out = _bridge({"op": "login_verify", "credential": text, "challenge": ch["challenge"], "origin": origin, "rp_id": rp_id,
                   "public_key": row["public_key"], "sign_count": row["sign_count"]})
    if not out.get("ok"):
        raise HttpError(401, "パスキーを確かめられなかった", code="passkey_invalid")
    with _app().db.tx() as c:
        c.execute("UPDATE passkeys SET sign_count=?, last_used_at=? WHERE id=?", (int(out["sign_count"]), dbm.now_iso(), row["id"]))
    token, csrf = _app().auth.new_session(row["user_id"])
    _app().db.audit(None, f"user:{row['user_id']}", "passkey_login", None)
    resp = Response.json({"ok": True, "csrf": csrf})
    resp.headers["Set-Cookie"] = session_cookie(token, _app().cfg.session_hours * 3600)
    return resp
