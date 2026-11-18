"""SQLite の保存（アプリの状態）。

家族の事実・判断そのものは世帯ごとの台帳（事実台帳・判断台帳・beancount）に置き、ここには置かない。
ここに置くのは、アカウント・人の表示名・同意・証憑（写真）の目録・確認待ちの提案・計算のジョブと結果の目録・注入データ・設定。
マイナンバーを保存する欄は作らない。
"""

from __future__ import annotations

import datetime as _dt
import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  login TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  pw_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  disabled INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS households (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- アカウントと世帯の所属。person_id は台帳の人の ID（p-…）。役割：admin（世帯の設定を変えられる）・member
CREATE TABLE IF NOT EXISTS memberships (
  user_id TEXT NOT NULL REFERENCES users(id),
  household_id TEXT NOT NULL REFERENCES households(id),
  role TEXT NOT NULL CHECK (role IN ('admin','member')),
  person_id TEXT NOT NULL,
  PRIMARY KEY (user_id, household_id)
);

-- 人の表示名（台帳には名前を書かない。名前はここだけ）。managed=1 はアカウントを持たず、管理する人が代わりに決める人（小さい子など）
CREATE TABLE IF NOT EXISTS persons (
  household_id TEXT NOT NULL REFERENCES households(id),
  person_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (household_id, person_id)
);

-- アカウントのない人を代わりに管理する人（同意・判断を代わりにする）
CREATE TABLE IF NOT EXISTS person_managers (
  household_id TEXT NOT NULL,
  person_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  PRIMARY KEY (household_id, person_id, user_id)
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  csrf TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

-- エージェント（MCP・外部 API）のトークン。scopes：read・propose。書き込み（確定）の権限はない
CREATE TABLE IF NOT EXISTS api_tokens (
  id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  user_id TEXT NOT NULL,
  household_id TEXT NOT NULL,
  label TEXT NOT NULL,
  scopes TEXT NOT NULL,
  external INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  revoked_at TEXT,
  last_used_at TEXT
);

-- 同意（追記のみ。現在の値は人 × 種類ごとの最後の行）
CREATE TABLE IF NOT EXISTS consents (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  household_id TEXT NOT NULL,
  person_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  value INTEGER NOT NULL,
  decided_by TEXT NOT NULL,
  decided_at TEXT NOT NULL,
  note TEXT
);

-- 証憑（アップロードした原本）。原本は書き換えない。sha256 で同定する
CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY,
  household_id TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  ext TEXT NOT NULL,
  mime TEXT NOT NULL,
  size INTEGER NOT NULL,
  owner_person TEXT NOT NULL,
  uploaded_by TEXT NOT NULL,
  uploaded_at TEXT NOT NULL,
  label TEXT,
  doc_type TEXT,
  ignored INTEGER NOT NULL DEFAULT 0,
  UNIQUE (household_id, sha256)
);

-- 証憑と台帳の記録の ID の結びつき（追記のみ。外すときは unlinked_at を入れる）
CREATE TABLE IF NOT EXISTS evidence_links (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  household_id TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  record_id TEXT NOT NULL,
  linked_by TEXT NOT NULL,
  linked_at TEXT NOT NULL
);

-- 確認待ち：OCR・AI・エージェント・人の下書き。人が確かめて「確定」を押すまで台帳に書かない
CREATE TABLE IF NOT EXISTS proposals (
  id TEXT PRIMARY KEY,
  household_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  rationale TEXT,
  candidates TEXT,
  evidence_id TEXT,
  origin TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  decided_by TEXT,
  decided_at TEXT,
  decision_note TEXT,
  result_record_id TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  household_id TEXT NOT NULL,
  status TEXT NOT NULL,
  stage TEXT,
  query TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error TEXT,
  result_hash TEXT
);

CREATE TABLE IF NOT EXISTS results (
  input_hash TEXT PRIMARY KEY,
  household_id TEXT NOT NULL,
  okura_gov_commit TEXT NOT NULL,
  created_at TEXT NOT NULL,
  ledger_digest TEXT NOT NULL,
  query TEXT NOT NULL
);

-- 注入データ（市町村・保険者ごとの値。出典の URL 必須）。外すときは retired_at を入れる（消さない）
CREATE TABLE IF NOT EXISTS injections (
  id TEXT PRIMARY KEY,
  household_id TEXT NOT NULL,
  entry TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  retired_at TEXT,
  retired_by TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  household_id TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  updated_by TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (household_id, key)
);

CREATE TABLE IF NOT EXISTS chats (
  id TEXT PRIMARY KEY,
  household_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  external INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chat_messages (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- 回答の依頼（招待リンク）。リンクは1回だけ使える。使った端末をその人に結び付ける（guest_sessions）。
-- email：手前の認証（Access など）で確かめるメール（任意）。claimed_email：実際に確かめたメール
CREATE TABLE IF NOT EXISTS invites (
  id TEXT PRIMARY KEY,
  household_id TEXT NOT NULL,
  person_id TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  email TEXT,
  question_ids TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  claimed_at TEXT,
  claimed_email TEXT,
  revoked_at TEXT
);

-- 招待リンクで登録した端末（その人あての質問に答えるだけ。ほかの API は使えない）
CREATE TABLE IF NOT EXISTS guest_sessions (
  token_hash TEXT PRIMARY KEY,
  invite_id TEXT NOT NULL,
  household_id TEXT NOT NULL,
  person_id TEXT NOT NULL,
  csrf TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  revoked_at TEXT
);

-- 家計簿の勘定（口座・カテゴリ）の画面の情報。台帳（book.jsonl）には英数字の勘定の名前だけを書く。
-- kind：bank・card・cash・emoney・other（口座）、expense・income（カテゴリ）。
-- 口座の見える範囲：shared=1 は家族の共有、0 は自分だけ（持ち主と、その人を管理する人だけ。合計にも入れない）。hidden：カテゴリを隠す（消さない）
-- source・source_key：取り込みの取得元の口座（同じ口座に取り込む）
CREATE TABLE IF NOT EXISTS book_accounts (
  household_id TEXT NOT NULL,
  account TEXT NOT NULL,
  label TEXT NOT NULL,
  kind TEXT NOT NULL,
  parent TEXT,
  icon TEXT,
  owner_person TEXT,
  source TEXT,
  source_key TEXT,
  shared INTEGER NOT NULL DEFAULT 0,
  hidden INTEGER NOT NULL DEFAULT 0,
  sort INTEGER NOT NULL DEFAULT 0,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  retired_at TEXT,
  PRIMARY KEY (household_id, account)
);

-- 取り込み待ち（取得元が API で送った取引のまとまり）。人が確定すると家計簿の台帳に入る。消さずに印を付ける
CREATE TABLE IF NOT EXISTS book_imports (
  id TEXT PRIMARY KEY,
  household_id TEXT NOT NULL,
  source TEXT NOT NULL,
  account_key TEXT NOT NULL,
  account_info TEXT NOT NULL,
  items TEXT NOT NULL,
  balance TEXT,
  received_by TEXT NOT NULL,
  received_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','confirmed','rejected')),
  decided_by TEXT,
  decided_at TEXT
);

-- 分類ルール：お店の文字を含む取引を、このカテゴリ（または振替先の口座）にする。外すときは retired_at
CREATE TABLE IF NOT EXISTS book_rules (
  id TEXT PRIMARY KEY,
  household_id TEXT NOT NULL,
  pattern TEXT NOT NULL,
  category TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  retired_at TEXT
);

-- 家計簿の予算（大項目ごとの毎月の金額）。追記のみ：カテゴリごとの最後の行が今の値（amount が NULL は予算なし）
CREATE TABLE IF NOT EXISTS book_budgets (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  household_id TEXT NOT NULL,
  category TEXT NOT NULL,
  amount INTEGER,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- 繰り返しの入力（毎日・毎週・毎月・月末）。人が決めた規則で、家計簿の画面を開いたときに期日の分を記録する。止めるときは stopped_at
CREATE TABLE IF NOT EXISTS book_recurring (
  id TEXT PRIMARY KEY,
  household_id TEXT NOT NULL,
  account TEXT NOT NULL,
  category TEXT NOT NULL,
  amount INTEGER NOT NULL,
  payee TEXT,
  memo TEXT,
  freq TEXT NOT NULL CHECK (freq IN ('daily','weekly','monthly','monthend')),
  start_on TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  stopped_at TEXT
);

-- 家計簿の入出金を申告の記録（事実台帳）に使ったつながり
CREATE TABLE IF NOT EXISTS book_tax_links (
  household_id TEXT NOT NULL,
  txn_id TEXT NOT NULL,
  record_id TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (household_id, txn_id, record_id)
);

-- パスキー（WebAuthn）。id は認証器の資格情報の ID（base64url）。user_handle はアカウントごとの乱数（名前を入れない）
CREATE TABLE IF NOT EXISTS passkeys (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  user_handle TEXT NOT NULL,
  public_key TEXT NOT NULL,
  sign_count INTEGER NOT NULL DEFAULT 0,
  label TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  revoked_at TEXT
);

-- パスキーの challenge（サーバーが作り、1回だけ・5分で切れる）
CREATE TABLE IF NOT EXISTS passkey_challenges (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  challenge TEXT NOT NULL,
  user_id TEXT,
  user_handle TEXT,
  created_at TEXT NOT NULL,
  used_at TEXT
);

-- 操作の記録（値や名前は書かない。何を・誰が・いつ）
CREATE TABLE IF NOT EXISTS audit (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  household_id TEXT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  target TEXT,
  at TEXT NOT NULL
);
"""


def now() -> _dt.datetime:
    """日本の時刻（時差つき、秒まで）。"""
    return _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9))).replace(microsecond=0)


def now_iso() -> str:
    return now().isoformat()


def new_id(prefix: str, nbytes: int = 8) -> str:
    """ASCII の ID（okura_ir の id の形：英数字で始まる、64文字まで）。"""
    return f"{prefix}-{secrets.token_hex(nbytes)}"


class Database:
    """スレッドごとに接続を持つ。書き込みはロックで直列にする。"""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self.write_lock = threading.RLock()
        with self.write_lock:
            c = self.conn()
            c.executescript(SCHEMA)  # executescript はそれ自体で確定する
            c.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))

    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys = ON")
            c.execute("PRAGMA journal_mode = WAL")
            self._local.conn = c
        return c

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self.write_lock:
            c = self.conn()
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
            except BaseException:
                c.execute("ROLLBACK")
                raise
            else:
                c.execute("COMMIT")

    def one(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        return self.conn().execute(sql, args).fetchone()

    def all(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        return self.conn().execute(sql, args).fetchall()

    def audit(self, household_id: str | None, actor: str, action: str, target: str | None = None) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO audit(household_id, actor, action, target, at) VALUES (?,?,?,?,?)",
                (household_id, actor, action, target, now_iso()),
            )

    # 設定 ------------------------------------------------------------------
    def get_setting(self, household_id: str, key: str, default: Any = None) -> Any:
        row = self.one("SELECT value FROM settings WHERE household_id=? AND key=?", (household_id, key))
        return default if row is None else json.loads(row["value"])

    def set_setting(self, household_id: str, key: str, value: Any, user_id: str) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO settings(household_id, key, value, updated_by, updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(household_id, key) DO UPDATE SET value=excluded.value, updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                (household_id, key, json.dumps(value, ensure_ascii=False), user_id, now_iso()),
            )
