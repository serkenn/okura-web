"""アプリの部品を組み立てる（DB・認証・okura-gov の窓口・台帳・計算のジョブ・結果）。"""

from __future__ import annotations

import datetime as _dt
import json
import threading
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import db as dbm
from .auth import Auth
from .config import Config
from .engine import Engine, EngineError, canonical, sha256_hex
from .ledgers import HouseholdLedger
from .results import LoadedResult, ResultStore, digest

if TYPE_CHECKING:
    from .book import Book


def default_query(today: _dt.date | None = None) -> dict[str, Any]:
    """既定の問い。対象の範囲（所得税 令和7・8年分、住民税・国保・国年 2026・2027年度、判定日 2025-01-01〜2027-12-31）。"""
    today = today or dbm.now().date()
    dates = sorted({today.isoformat(), f"{today.year}-12-31"})
    return {
        "income_tax_years": [2025, 2026],
        "filing_date": {"on": "2027-03-15", "planned": True},
        "resident_tax_fiscal_years": [2026, 2027],
        "kokuho_fiscal_years": [2026, 2027],
        "kokunen_fiscal_years": [2026, 2027],
        "dependent_judgment_dates": dates,
        "scenarios": [],
        "forms": {"persons": None},
    }


class App:
    def __init__(self, cfg: Config, *, start_worker: bool = True):
        self.cfg = cfg
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = dbm.Database(cfg.db_path)
        self.auth = Auth(self.db, cfg.session_hours)
        self.engine = Engine(cfg)
        self.results = ResultStore()
        self._ledgers: dict[str, HouseholdLedger] = {}
        self._wake = threading.Event()
        self._stop = threading.Event()
        with self.db.tx() as c:
            c.execute(
                "UPDATE jobs SET status='failed', error='サーバーの停止で中断した。もう一度計算する', finished_at=? WHERE status IN ('running','queued')",
                (dbm.now_iso(),),
            )
        self.worker: threading.Thread | None = None
        threading.Thread(target=self._warm, name="okura-meta", daemon=True).start()
        if start_worker:
            self.worker = threading.Thread(target=self._loop, name="okura-calc", daemon=True)
            self.worker.start()

    # ------------------------------------------------------------------ 台帳
    def ledger(self, household_id: str) -> HouseholdLedger:
        lg = self._ledgers.get(household_id)
        if lg is None:
            lg = self._ledgers[household_id] = HouseholdLedger(self.cfg.data_dir, self.engine, household_id)
        return lg

    def book(self, household_id: str) -> "Book":
        from .book import Book

        books = self.__dict__.setdefault("_books", {})
        if household_id not in books:
            books[household_id] = Book(self.ledger(household_id).dir.parent, household_id, self.engine)
        return books[household_id]

    def meta(self) -> dict[str, Any]:
        return self.engine.meta()

    def injected(self, household_id: str) -> list[dict[str, Any]] | None:
        rows = self.db.all("SELECT entry FROM injections WHERE household_id=? AND retired_at IS NULL ORDER BY created_at", (household_id,))
        entries = [json.loads(r["entry"]) for r in rows]
        return entries or None

    def _warm(self) -> None:
        try:
            self.engine.meta()  # 語彙・注入点の読み込み（サブプロセス。数秒）を先に済ませる
        except EngineError:
            pass

    # ------------------------------------------------------------------ 計算のジョブ
    def enqueue(self, household_id: str, user_id: str, query: dict[str, Any] | None = None) -> str:
        q = query or self.db.get_setting(household_id, "default_query") or default_query()
        qj = json.dumps(q, ensure_ascii=False, sort_keys=True)
        with self.db.tx() as c:
            row = c.execute(
                "SELECT id FROM jobs WHERE household_id=? AND status='queued' AND query=?", (household_id, qj)
            ).fetchone()
            if row is not None:
                return row["id"]
            jid = dbm.new_id("job", 6)
            c.execute(
                "INSERT INTO jobs(id, household_id, status, stage, query, created_by, created_at) VALUES (?,?,?,?,?,?,?)",
                (jid, household_id, "queued", "順番待ち", qj, user_id, dbm.now_iso()),
            )
        self._wake.set()
        return jid

    def _loop(self) -> None:
        while not self._stop.is_set():
            row = self.db.one("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1")
            if row is None:
                self._wake.wait(timeout=2.0)
                self._wake.clear()
                continue
            self._run_job(dict(row))

    def _stage(self, jid: str, stage: str, **extra: Any) -> None:
        sets = ["stage=?"]
        args: list[Any] = [stage]
        for k, v in extra.items():
            sets.append(f"{k}=?")
            args.append(v)
        args.append(jid)
        with self.db.tx() as c:
            c.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id=?", tuple(args))

    def _run_job(self, job: dict[str, Any]) -> None:
        jid, hid = job["id"], job["household_id"]
        self._stage(jid, "データベースの記録から計算の入力を作っている", status="running", started_at=dbm.now_iso())
        try:
            lg = self.ledger(hid)
            ir = lg.get_ir()
            query = json.loads(job["query"])
            injected = self.injected(hid)
            gov = self.engine.okura_gov_version()
            input_hash = sha256_hex(canonical({"ir": ir, "query": query, "injected": injected, "okura_gov": gov.get("commit")}))
            path = lg.results_dir / f"{input_hash}.json"
            if not path.exists():
                self._stage(jid, "判定コアで計算している（家族全体で数十秒かかる）")
                out = self.engine.evaluate(ir, query, injected)
                lg.results_dir.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".part")
                tmp.write_bytes(out)
                tmp.replace(path)
            self._stage(jid, "結果をまとめている")
            dpath = lg.results_dir / f"{input_hash}.digest.json"
            if not dpath.exists():
                lr = self.results.load(path)
                d = digest(lr, okura_gov=gov)
                dpath.write_bytes(json.dumps(d, ensure_ascii=False).encode("utf-8"))
            with self.db.tx() as c:
                c.execute(
                    "INSERT OR IGNORE INTO results(input_hash, household_id, okura_gov_commit, created_at, ledger_digest, query) VALUES (?,?,?,?,?,?)",
                    (input_hash, hid, gov.get("commit") or "", dbm.now_iso(), lg.digest(), job["query"]),
                )
                c.execute(
                    "UPDATE jobs SET status='done', stage='完了', finished_at=?, result_hash=? WHERE id=?",
                    (dbm.now_iso(), input_hash, jid),
                )
        except EngineError as e:
            err = {"message": str(e), "code": e.code, "problems": e.problems[:50]}
            with self.db.tx() as c:
                c.execute(
                    "UPDATE jobs SET status='failed', stage='失敗', finished_at=?, error=? WHERE id=?",
                    (dbm.now_iso(), json.dumps(err, ensure_ascii=False), jid),
                )
        except Exception as e:  # noqa: BLE001 - ジョブの誤りは記録して次へ（中身はログに出さない）
            err = {"message": "アプリの内部の誤り", "code": "internal", "type": type(e).__name__}
            traceback.print_exception(type(e), e, None)  # 型と場所だけ（値は出さない）
            with self.db.tx() as c:
                c.execute(
                    "UPDATE jobs SET status='failed', stage='失敗', finished_at=?, error=? WHERE id=?",
                    (dbm.now_iso(), json.dumps(err, ensure_ascii=False), jid),
                )

    # ------------------------------------------------------------------ 結果
    def latest_result(self, household_id: str) -> dict[str, Any] | None:
        row = self.db.one(
            "SELECT j.*, r.ledger_digest FROM jobs j LEFT JOIN results r ON r.input_hash=j.result_hash "
            "WHERE j.household_id=? AND j.status='done' ORDER BY j.finished_at DESC LIMIT 1",
            (household_id,),
        )
        return dict(row) if row else None

    def input_hash(self, household_id: str, query: dict[str, Any]) -> str:
        """計算の入力（中間表現・問い・注入データ・okura-gov の版）のハッシュ。結果の ID と同じ作り方。"""
        ir = self.ledger(household_id).get_ir()
        gov = self.engine.okura_gov_version()
        return sha256_hex(canonical({"ir": ir, "query": query, "injected": self.injected(household_id), "okura_gov": gov.get("commit")}))

    def is_stale(self, household_id: str, lr: dict[str, Any]) -> bool:
        """最新の結果が古いか。台帳のファイルが変わっても、計算に使う中身が同じなら古くない
        （家計簿の取引など、事実の種類のない取引は中間表現に入らない）。"""
        try:
            d = self.ledger(household_id).digest()
            if lr.get("ledger_digest") == d:
                return False
            key = (household_id, lr["result_hash"], d, len(self.injected(household_id) or []))
            memo = self.__dict__.setdefault("_stale_memo", {})
            if key not in memo:
                if len(memo) > 32:
                    memo.clear()
                memo[key] = self.input_hash(household_id, json.loads(lr["query"])) != lr["result_hash"]
            return memo[key]
        except (EngineError, OSError, ValueError, KeyError):
            return True

    def result_paths(self, household_id: str, input_hash: str) -> tuple[Path, Path]:
        if not all(ch in "0123456789abcdef" for ch in input_hash) or len(input_hash) != 64:
            raise ValueError("結果の ID の形が違う")
        lg = self.ledger(household_id)
        return lg.results_dir / f"{input_hash}.json", lg.results_dir / f"{input_hash}.digest.json"

    def load_result(self, household_id: str, input_hash: str) -> LoadedResult:
        path, _ = self.result_paths(household_id, input_hash)
        return self.results.load(path)

    def load_digest(self, household_id: str, input_hash: str) -> dict[str, Any]:
        key = (household_id, input_hash)
        cache = self.__dict__.setdefault("_digest_cache", {})
        if key in cache:
            return cache[key]
        _, dpath = self.result_paths(household_id, input_hash)
        d = json.loads(dpath.read_bytes().decode("utf-8"))
        if len(cache) >= 6:
            cache.pop(next(iter(cache)))
        cache[key] = d
        return d

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
