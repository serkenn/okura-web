"""アカウント・セッション・エージェントのトークン（標準ライブラリだけ）。

- パスワードは scrypt（hashlib）でハッシュにして保存する。
- セッションの Cookie は HttpOnly・SameSite=Strict。状態を変えるリクエストには CSRF のトークン（ヘッダー）を求める。
- エージェントのトークン（MCP・外部 API）は「読む・計算する・説明する」（read）と「提案する」（propose）だけ。
  確定（台帳への書き込み）はできない。確定は画面で人が押す（⑬）。
"""

from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from typing import Any

from . import db as dbm

_N, _R, _P = 2**14, 8, 1

SCOPES = ("read", "propose", "import")  # import：家計簿の取り込み待ちに置くだけ（読めない・確定できない）


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt$%d$%d$%d$%s$%s" % (_N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def check_password_strength(password: str) -> str | None:
    if len(password) < 10:
        return "パスワードは10文字以上にする"
    return None


@dataclass
class Principal:
    """リクエストの主体。kind：session（画面の人）・token（エージェント）。"""

    kind: str
    user_id: str
    display_name: str
    household_id: str | None = None
    role: str | None = None
    person_id: str | None = None
    csrf: str | None = None
    token_id: str | None = None
    scopes: tuple[str, ...] = ()
    external: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_human(self) -> bool:
        return self.kind in ("session", "guest")

    @property
    def actor(self) -> str:
        if self.kind == "guest":
            return f"guest:{self.extra.get('invite_id')}"
        return f"user:{self.user_id}" if self.kind == "session" else f"token:{self.token_id}"


class Auth:
    def __init__(self, database: dbm.Database, session_hours: int):
        self.db = database
        self.session_hours = session_hours

    # ------------------------------------------------------------------ セッション
    def login(self, login: str, password: str) -> tuple[str, str] | None:
        row = self.db.one("SELECT * FROM users WHERE login=? AND disabled=0", (login,))
        if row is None:
            verify_password(password, hash_password("dummy-password-x"))  # 時間を揃える
            return None
        if not verify_password(password, row["pw_hash"]):
            return None
        return self.new_session(row["id"])

    def new_session(self, user_id: str) -> tuple[str, str]:
        """ログインのセッションを作る（パスワード・パスキーのどちらでも）。"""
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        now = dbm.now()
        with self.db.tx() as c:
            c.execute("DELETE FROM sessions WHERE expires_at < ?", (now.isoformat(),))
            c.execute(
                "INSERT INTO sessions(token_hash, user_id, csrf, created_at, expires_at) VALUES (?,?,?,?,?)",
                (_token_hash(token), user_id, csrf, now.isoformat(), (now + _dt.timedelta(hours=self.session_hours)).isoformat()),
            )
        return token, csrf

    def logout(self, token: str) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))

    def session(self, token: str | None) -> Principal | None:
        if not token:
            return None
        row = self.db.one(
            "SELECT s.csrf, s.expires_at, u.id, u.display_name FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=? AND u.disabled=0",
            (_token_hash(token),),
        )
        if row is None or row["expires_at"] < dbm.now_iso():
            return None
        p = Principal("session", row["id"], row["display_name"], csrf=row["csrf"])
        m = self.db.one("SELECT household_id, role, person_id FROM memberships WHERE user_id=? LIMIT 1", (row["id"],))
        if m is not None:
            p.household_id, p.role, p.person_id = m["household_id"], m["role"], m["person_id"]
        return p

    # ------------------------------------------------------------------ 招待リンク（回答の依頼）
    INVITE_DAYS_MAX = 30
    GUEST_DAYS = 30

    def create_invite(
        self, household_id: str, person_id: str, created_by: str, *, email: str | None, question_ids: list[str] | None, days: int
    ) -> tuple[str, str]:
        """招待リンクの秘密（URL に入れる）と ID。秘密はハッシュだけを保存する。"""
        days = max(1, min(int(days), self.INVITE_DAYS_MAX))
        token = secrets.token_urlsafe(32)
        iid = dbm.new_id("inv", 6)
        now = dbm.now()
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO invites(id, household_id, person_id, token_hash, email, question_ids, created_by, created_at, expires_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    iid, household_id, person_id, _token_hash(token), email,
                    ",".join(question_ids) if question_ids else None, created_by,
                    now.isoformat(), (now + _dt.timedelta(days=days)).isoformat(),
                ),
            )
        return iid, token

    def claim_invite(self, token: str, verified_email: str | None) -> tuple[str, str, dict[str, Any]] | str:
        """招待リンクを使う。成功なら (端末の秘密, csrf, 招待)、失敗なら理由。

        - 1回だけ（使った後・期限切れ・取消し後は使えない）
        - 招待にメールがあり、手前の認証で確かめたメールがあれば、一致を求める
        """
        if not token or len(token) > 200:
            return "リンクの形が違う"
        now = dbm.now()
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM invites WHERE token_hash=?", (_token_hash(token),)).fetchone()
            if row is None:
                return "このリンクは使えない"
            if row["revoked_at"]:
                return "このリンクは取り消された"
            if row["claimed_at"]:
                return "このリンクはもう使われた（使ったのが自分でなければ、送った人に知らせる）"
            if row["expires_at"] < now.isoformat():
                return "このリンクは期限が切れた"
            if row["email"] and verified_email and row["email"] != verified_email:
                return "このリンクは別のメールアドレスの人あて"
            device = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(24)
            c.execute("UPDATE invites SET claimed_at=?, claimed_email=? WHERE id=?", (now.isoformat(), verified_email, row["id"]))
            c.execute(
                "INSERT INTO guest_sessions(token_hash, invite_id, household_id, person_id, csrf, created_at, expires_at) VALUES (?,?,?,?,?,?,?)",
                (_token_hash(device), row["id"], row["household_id"], row["person_id"], csrf, now.isoformat(),
                 (now + _dt.timedelta(days=self.GUEST_DAYS)).isoformat()),
            )
        return device, csrf, dict(row)

    def guest(self, token: str | None) -> Principal | None:
        if not token:
            return None
        row = self.db.one(
            "SELECT g.*, i.question_ids, i.revoked_at AS invite_revoked FROM guest_sessions g JOIN invites i ON i.id=g.invite_id "
            "WHERE g.token_hash=?",
            (_token_hash(token),),
        )
        if row is None or row["revoked_at"] or row["invite_revoked"] or row["expires_at"] < dbm.now_iso():
            return None
        name = self.db.one("SELECT display_name FROM persons WHERE household_id=? AND person_id=?", (row["household_id"], row["person_id"]))
        return Principal(
            "guest",
            f"guest:{row['invite_id']}",
            name["display_name"] if name else "",
            household_id=row["household_id"],
            role="guest",
            person_id=row["person_id"],
            csrf=row["csrf"],
            extra={"invite_id": row["invite_id"], "question_ids": [q for q in (row["question_ids"] or "").split(",") if q]},
        )

    def revoke_invite(self, household_id: str, invite_id: str) -> bool:
        now = dbm.now_iso()
        with self.db.tx() as c:
            n = c.execute("UPDATE invites SET revoked_at=? WHERE id=? AND household_id=? AND revoked_at IS NULL", (now, invite_id, household_id)).rowcount
            c.execute("UPDATE guest_sessions SET revoked_at=? WHERE invite_id=? AND revoked_at IS NULL", (now, invite_id))
        return n > 0

    # ------------------------------------------------------------------ トークン
    def create_token(self, user_id: str, household_id: str, label: str, scopes: list[str], external: bool) -> tuple[str, str]:
        bad = [s for s in scopes if s not in SCOPES]
        if bad or not scopes:
            raise ValueError(f"scopes は {SCOPES} から選ぶ")
        token = "okt_" + secrets.token_urlsafe(32)
        tid = dbm.new_id("tok", 6)
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO api_tokens(id, token_hash, user_id, household_id, label, scopes, external, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (tid, _token_hash(token), user_id, household_id, label, ",".join(scopes), 1 if external else 0, dbm.now_iso()),
            )
        return tid, token

    def token(self, bearer: str | None) -> Principal | None:
        if not bearer or not bearer.startswith("okt_"):
            return None
        row = self.db.one(
            "SELECT t.*, u.display_name FROM api_tokens t JOIN users u ON u.id=t.user_id WHERE t.token_hash=? AND t.revoked_at IS NULL AND u.disabled=0",
            (_token_hash(bearer),),
        )
        if row is None:
            return None
        m = self.db.one(
            "SELECT role, person_id FROM memberships WHERE user_id=? AND household_id=?", (row["user_id"], row["household_id"])
        )
        if m is None:
            return None
        with self.db.tx() as c:
            c.execute("UPDATE api_tokens SET last_used_at=? WHERE id=?", (dbm.now_iso(), row["id"]))
        return Principal(
            "token",
            row["user_id"],
            row["display_name"],
            household_id=row["household_id"],
            role=m["role"],
            person_id=m["person_id"],
            token_id=row["id"],
            scopes=tuple(s for s in row["scopes"].split(",") if s),
            external=bool(row["external"]),
        )
