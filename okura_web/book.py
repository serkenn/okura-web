"""家計簿の台帳（複式簿記）。申告の台帳（ledger/）とは別の置き場所に置き、判定コアの計算には入れない。

    data/households/<世帯ID>/book/
        book.jsonl        出来事の記録（追記のみ・ハッシュの鎖）。これが正本
        book.beancount    出来事から作る beancount の台帳（写し。いつでも作り直せる。Fava などで見られる）

- 出来事：open（勘定を開く）・add（取引を足す）・correct（取引を直す）・delete（取引を取り消す。理由つき）・balance（残高の確認）。
  上書きしない。直すときは correct を足す（⑫ 追記のみ）。
- 書くときは、写しに足して beancount を作り、okura-gov の記録層の安全な読み込み（transactions）で確かめてから置き換える。
- Web のサーバーは beancount を import しない。beancount の文字を作るだけ（読むのは記録層のサブプロセス）。
- 勘定の名前は英数字（beancount の決まり）。画面の名前（日本語）・持ち主・アイコンは SQLite（book_accounts）に置く。
- 金額は整数の円。勘定は円だけ（記録層の決まり）。
- ハッシュの鎖で途中の行の書き換え・削除は見つかる。最後の行の書き換え・切り詰めは見つけられない（記録層の台帳と同じ限り。records README §4.2）。
"""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .engine import Engine, EngineError
from .ledgers import household_lock

ACCOUNT_RE = re.compile(r"^(Assets|Liabilities|Expenses|Income|Equity)(:[A-Z0-9][A-Za-z0-9-]{0,40}){1,4}$")
TX_ID_RE = re.compile(r"^bk-[0-9a-f]{12}$")
SOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_AMOUNT = 10**12
OPS = ("open", "add", "correct", "delete", "balance")
OPEN_ON = "2000-01-01"  # 勘定を開く日（取引より前ならよい）

# beancount の記録層が拒否する文字（制御文字・C1・行区切り・双方向の書式）を落とす
_BAD_CHARS = re.compile("[\x00-\x1f\x7f-\x9f  ‎‏‪-‮⁦-⁩]")


class BookError(Exception):
    def __init__(self, message: str, *, code: str = "book_error", problems: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.code = code
        self.problems = problems or []


def clean_text(s: Any, limit: int = 200) -> str:
    if not isinstance(s, str):
        return ""
    return _BAD_CHARS.sub(" ", s).strip()[:limit]


def valid_date(s: Any) -> bool:
    if not isinstance(s, str) or not DATE_RE.match(s):
        return False
    try:
        _dt.date.fromisoformat(s)
    except ValueError:
        return False
    return True


def new_tx_id(seed: str) -> str:
    return "bk-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def check_txn(t: Any) -> dict[str, Any]:
    """取引の形を確かめて、決まった形にして返す。postings の合計は 0（複式簿記）。"""
    if not isinstance(t, dict):
        raise BookError("取引の形が違う", code="bad_txn")
    tid = t.get("id")
    if not isinstance(tid, str) or not TX_ID_RE.match(tid):
        raise BookError("取引の ID の形が違う", code="bad_txn")
    if not valid_date(t.get("date")):
        raise BookError("日付は YYYY-MM-DD", code="bad_date")
    posts = t.get("postings")
    if not isinstance(posts, list) or not 2 <= len(posts) <= 20:
        raise BookError("仕訳は2行から20行", code="bad_postings")
    out_posts = []
    for p in posts:
        if not isinstance(p, dict) or not isinstance(p.get("account"), str) or not ACCOUNT_RE.match(p["account"]):
            raise BookError("勘定の名前の形が違う", code="bad_account")
        a = p.get("amount")
        if not isinstance(a, int) or isinstance(a, bool) or abs(a) > MAX_AMOUNT:
            raise BookError("金額は整数の円", code="bad_amount")
        out_posts.append({"account": p["account"], "amount": a})
    if sum(p["amount"] for p in out_posts) != 0:
        raise BookError("借方と貸方が合わない（合計が 0 でない）", code="unbalanced")
    out = {"id": tid, "date": t["date"], "payee": clean_text(t.get("payee"), 120), "narration": clean_text(t.get("narration"), 200),
           "postings": out_posts}
    src, sid = t.get("source"), t.get("source_id")
    if src is not None or sid is not None:
        if not (isinstance(src, str) and SOURCE_RE.match(src) and isinstance(sid, str) and 0 < len(sid) <= 200):
            raise BookError("取得元の形が違う", code="bad_source")
        out["source"], out["source_id"] = src, clean_text(sid, 200)
    if t.get("memo"):
        out["memo"] = clean_text(t.get("memo"), 500)
    if t.get("excluded") is True:
        out["excluded"] = True  # 計算対象外（収支の合計に入れない）
    return out


@dataclass
class BookState:
    accounts: dict[str, str] = field(default_factory=dict)  # 勘定 → 開いた日
    txns: dict[str, dict[str, Any]] = field(default_factory=dict)  # 取消しを除いた今の取引
    deleted: set[str] = field(default_factory=set)
    balances: list[dict[str, Any]] = field(default_factory=list)
    sources: dict[tuple[str, str], str] = field(default_factory=dict)  # (取得元, 取得元の ID) → 今ある取引の ID
    head: str = ""
    count: int = 0


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _apply(st: BookState, e: dict[str, Any], i: int) -> None:
    op = e["op"]
    if op == "open":
        st.accounts.setdefault(e["account"], OPEN_ON)
    elif op in ("add", "correct"):
        t = e["txn"]
        if op == "add" and (t["id"] in st.txns or t["id"] in st.deleted):
            raise BookError(f"家計簿の記録の {i + 1} 行目：同じ ID の取引がある", code="book_dup")
        if op == "correct" and t["id"] not in st.txns:
            raise BookError(f"家計簿の記録の {i + 1} 行目：直す取引がない", code="book_correct_unknown")
        st.txns[t["id"]] = t
        if t.get("source"):
            st.sources[(t["source"], t["source_id"])] = t["id"]
    elif op == "delete":
        if e["id"] not in st.txns:
            raise BookError(f"家計簿の記録の {i + 1} 行目：取り消す取引がない", code="book_delete_unknown")
        t = st.txns.pop(e["id"])
        st.deleted.add(e["id"])
        if t.get("source") and st.sources.get((t["source"], t["source_id"])) == t["id"]:
            # 取り消した取引の取得元の ID は外す（「元に戻す」のあとに登録し直せる）。二重の取り込みは取り込みの記録（book_imports）で防ぐ
            del st.sources[(t["source"], t["source_id"])]
    elif op == "balance":
        st.balances.append({"account": e["account"], "date": e["date"], "amount": e["amount"]})


def fold(lines: list[bytes]) -> BookState:
    """出来事の記録を順にたどって今の状態にする。鎖が切れていたら止める（改ざん・壊れ）。"""
    st = BookState()
    prev = ""
    for i, raw in enumerate(lines):
        try:
            e = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as ex:
            raise BookError(f"家計簿の記録の {i + 1} 行目を読めない", code="book_corrupt") from ex
        if not isinstance(e, dict) or e.get("prev") != prev or e.get("seq") != i + 1 or e.get("op") not in OPS:
            raise BookError(f"家計簿の記録の {i + 1} 行目で鎖が切れている", code="book_chain")
        prev = hashlib.sha256(raw).hexdigest()
        _apply(st, e, i)
    st.head, st.count = prev, len(lines)
    return st


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(st: BookState) -> str:
    """今の状態から beancount の文字を作る（同じ状態なら同じ文字）。"""
    out = [
        "; okura-web の家計簿（book.jsonl から作った写し。手で直さない。直すとアプリが作り直すときに消える）",
        'option "operating_currency" "JPY"',
        "",
    ]
    for acc in sorted(st.accounts):
        out.append(f"{st.accounts[acc]} open {acc} JPY")
    out.append("")
    for t in sorted(st.txns.values(), key=lambda x: (x["date"], x["id"])):
        out.append(f"{t['date']} * {_q(t.get('payee') or '')} {_q(t.get('narration') or '')}")
        out.append(f"  id: {_q(t['id'])}")
        if t.get("source"):
            out.append(f"  x_source: {_q(t['source'])}")
            out.append(f"  x_source_id: {_q(t['source_id'])}")
        if t.get("memo"):
            out.append(f"  memo: {_q(t['memo'])}")
        if t.get("excluded"):
            out.append("  x_excluded: TRUE")
        for p in t["postings"]:
            out.append(f"  {p['account']}  {p['amount']} JPY")
        out.append("")
    for b in balance_checks(st):
        if b["ok"]:
            # beancount の balance はその日の始まりの残高。取得元の「その日の終わりの残高」は翌日に置く。
            # 合わない残高は台帳に書かない（取引の取りこぼしで台帳全体が読めなくなるのを避ける）。画面で「合わない」と出す
            d = (_dt.date.fromisoformat(b["date"]) + _dt.timedelta(days=1)).isoformat()
            out.append(f"{d} balance {b['account']}  {b['amount']} JPY")
    return "\n".join(out).rstrip("\n") + "\n"


def balance_checks(st: BookState) -> list[dict[str, Any]]:
    """残高の確認ごとに、台帳から計算した残高と合うか。同じ勘定・同じ日は最後のものだけ。"""
    last: dict[tuple[str, str], dict[str, Any]] = {}
    for b in st.balances:
        last[(b["account"], b["date"])] = b
    out = []
    for (acc, d), b in sorted(last.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        calc = sum(p["amount"] for t in st.txns.values() if t["date"] <= d for p in t["postings"] if p["account"] == acc)
        out.append({"account": acc, "date": d, "amount": b["amount"], "calculated": calc, "ok": calc == b["amount"]})
    return out


class Book:
    def __init__(self, household_dir: Path, household_id: str, engine: Engine):
        self.dir = household_dir / "book"
        self.log = self.dir / "book.jsonl"
        self.beancount = self.dir / "book.beancount"
        self.household_id = household_id
        self.engine = engine
        self.lock = household_lock(household_id)
        self._cache: tuple[bytes, BookState] | None = None

    def _lines(self) -> list[bytes]:
        if not self.log.exists():
            return []
        data = self.log.read_bytes()
        return [ln for ln in data.split(b"\n") if ln]

    def state(self) -> BookState:
        with self.lock:
            raw = self.log.read_bytes() if self.log.exists() else b""
            key = hashlib.sha256(raw).digest()
            if self._cache and self._cache[0] == key:
                return self._cache[1]
            st = fold([ln for ln in raw.split(b"\n") if ln])
            self._cache = (key, st)
            return st

    def append(self, events: list[dict[str, Any]], *, by: str) -> BookState:
        """出来事を足す。写しで beancount を作って記録層で確かめてから置き換える。失敗は BookError。"""
        if not events:
            return self.state()
        with self.lock:
            st = self.state()
            prev, seq = st.head, st.count
            now = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9))).isoformat(timespec="seconds")
            new_lines = []
            st = copy.deepcopy(st)
            for ev in events:
                ev = self._check_event(ev, st)
                seq += 1
                line = _canon({**ev, "seq": seq, "prev": prev, "at": now, "by": by})
                new_lines.append(line)
                prev = hashlib.sha256(line).hexdigest()
                _apply(st, json.loads(line), seq - 1)  # 次の出来事の検査に今の状態を使う
            text = render(st)
            self.dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=self.dir, prefix="tmp-") as td:
                tmp = Path(td)
                (tmp / "book.beancount").write_bytes(text.encode("utf-8"))
                try:
                    self.engine.transactions_file(tmp / "book.beancount", tmp)
                except EngineError as e:
                    raise BookError("家計簿のデータベースとして読めない形になる", code="book_invalid", problems=e.problems) from e
                log_tmp = tmp / "book.jsonl"
                if self.log.exists():
                    shutil.copyfile(self.log, log_tmp)
                with log_tmp.open("ab") as f:
                    for ln in new_lines:
                        f.write(ln + b"\n")
                log_tmp.replace(self.log)
                (tmp / "book.beancount").replace(self.beancount)
            self._cache = None
            return self.state()

    @staticmethod
    def _check_event(ev: dict[str, Any], st: BookState) -> dict[str, Any]:
        op = ev.get("op")
        if op == "open":
            acc = ev.get("account")
            if not isinstance(acc, str) or not ACCOUNT_RE.match(acc):
                raise BookError("勘定の名前の形が違う", code="bad_account")
            return {"op": "open", "account": acc}
        if op in ("add", "correct"):
            t = check_txn(ev.get("txn"))
            for p in t["postings"]:
                if p["account"] not in st.accounts:
                    raise BookError(f"開いていない勘定（{p['account']}）", code="account_not_open")
            out: dict[str, Any] = {"op": op, "txn": t}
            if op == "correct":
                out["reason"] = clean_text(ev.get("reason"), 200) or "直した"
            return out
        if op == "delete":
            if ev.get("id") not in st.txns:
                raise BookError("取り消す取引がない", code="not_found")
            reason = clean_text(ev.get("reason"), 200)
            if not reason:
                raise BookError("取り消す理由が要る", code="reason_required")
            return {"op": "delete", "id": ev["id"], "reason": reason}
        if op == "balance":
            acc, d, a = ev.get("account"), ev.get("date"), ev.get("amount")
            if acc not in st.accounts or not valid_date(d) or not isinstance(a, int) or isinstance(a, bool) or abs(a) > MAX_AMOUNT:
                raise BookError("残高の確認の形が違う", code="bad_balance")
            return {"op": "balance", "account": acc, "date": d, "amount": a}
        raise BookError("知らない出来事", code="bad_op")
