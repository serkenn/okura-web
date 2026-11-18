"""世帯ごとの台帳（事実台帳・判断台帳・beancount）と証憑の置き場所。

置き場所（既定はローカル。data/ は git に入れない）：

    data/households/<世帯ID>/ledger/
        main.beancount     手で付けたい人のための beancount の台帳（アプリは最初に作るだけで書き換えない）
        facts.jsonl        事実台帳（追記のみ。アプリが入力した記録はここに書く）
        judgments.jsonl    判断台帳（追記のみ）
        evidence/<sha256>.<拡張子>   アップロードした原本（書き換えない。読み取り専用にする）
    data/households/<世帯ID>/results/<入力のハッシュ>.json   計算の結果（キャッシュ）

書き込みの流れ（`write`）：世帯のロック → 台帳の写しに記録層の `append` で足す → 写しで `build-ir` を通す
（中間表現の検査まで通ったものだけ）→ 写しを本物に置き換える。台帳を壊す書き込みは本物に届かない。
アプリが入力する取引の種類（給与・医療費など）は、記録層の約束（records README §4.3「事実台帳にも書ける」）どおり事実台帳に書く。
こうすると訂正・取消しも追記（op: correct・delete と理由）で残る。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import db as dbm
from .engine import Engine, EngineError

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()

MAIN_BEANCOUNT = """; okura-web が作った beancount の台帳。手で取引を付けるときはこのファイルに書く（アプリは書き換えない）。
; 書き方：vendor/okura-gov/packages/records/README.md §4.1。plugin 行・insert_pythonpath は記録層が拒否する。
option "operating_currency" "JPY"
"""

_ENTRY_NUM = re.compile(r"^(fe|je)-(\d+)$")


def household_lock(household_id: str) -> threading.RLock:
    with _LOCKS_GUARD:
        lock = _LOCKS.get(household_id)
        if lock is None:
            lock = _LOCKS[household_id] = threading.RLock()
        return lock


@dataclass
class WriteOutcome:
    entry_ids: list[str]
    ir: dict[str, Any]


class HouseholdLedger:
    def __init__(self, data_dir: Path, engine: Engine, household_id: str):
        if not re.fullmatch(r"hh-[0-9a-f]{16}", household_id):
            raise ValueError("世帯 ID の形が違う")
        self.household_id = household_id
        self.engine = engine
        self.base = data_dir / "households" / household_id
        self.dir = self.base / "ledger"
        self.evidence_dir = self.dir / "evidence"
        self.results_dir = self.base / "results"
        self.tmp_dir = self.base / "tmp"
        self.facts = self.dir / "facts.jsonl"
        self.judgments = self.dir / "judgments.jsonl"
        self.main = self.dir / "main.beancount"
        self._ir_cache: tuple[str, dict[str, Any]] | None = None

    # ------------------------------------------------------------------ 準備
    def ensure(self) -> None:
        for d in (self.dir, self.evidence_dir, self.results_dir, self.tmp_dir):
            d.mkdir(parents=True, exist_ok=True)
        if not self.main.exists():
            self.main.write_bytes(MAIN_BEANCOUNT.encode("utf-8"))
        for f in (self.facts, self.judgments):
            if not f.exists():
                f.write_bytes(b"")

    @property
    def lock(self) -> threading.RLock:
        return household_lock(self.household_id)

    # ------------------------------------------------------------------ 読む
    def digest(self) -> str:
        """台帳の中身のハッシュ（beancount の全ファイル・事実台帳・判断台帳）。中間表現のキャッシュの鍵。"""
        h = hashlib.sha256()
        files = sorted(p for p in self.dir.rglob("*.beancount") if "evidence" not in p.parts)
        for p in [*files, self.facts, self.judgments]:
            h.update(str(p.relative_to(self.dir)).encode("utf-8"))
            h.update(b"\0")
            h.update(p.read_bytes() if p.exists() else b"")
            h.update(b"\0")
        return h.hexdigest()

    def entries(self, which: str) -> list[dict[str, Any]]:
        path = self.facts if which == "facts" else self.judgments
        out: list[dict[str, Any]] = []
        if not path.exists():
            return out
        for line in path.read_bytes().decode("utf-8").split("\n"):
            if line.strip():
                out.append(json.loads(line))
        return out

    def heads(self, which: str) -> dict[str, dict[str, Any]]:
        """record.id → その記録の置き換えの連鎖の先頭の行（取り消した記録は op=delete の行）。"""
        by_entry: dict[str, dict[str, Any]] = {}
        head_of_record: dict[str, str] = {}
        record_of_entry: dict[str, str] = {}
        for e in self.entries(which):
            by_entry[e["entry_id"]] = e
            if e["op"] == "add":
                rid = e["record"]["id"]
            else:
                rid = record_of_entry.get(e.get("replaces", ""), "")
            record_of_entry[e["entry_id"]] = rid
            head_of_record[rid] = e["entry_id"]
        return {rid: by_entry[eid] for rid, eid in head_of_record.items() if rid}

    def history(self, record_id: str) -> list[dict[str, Any]]:
        """その記録の行の履歴（追加・訂正・取消し）。判断の見直し（record.replaces）は別の記録として残る。"""
        out = []
        for which in ("facts", "judgments"):
            record_of_entry: dict[str, str] = {}
            for e in self.entries(which):
                rid = e["record"]["id"] if e["op"] == "add" else record_of_entry.get(e.get("replaces", ""), "")
                record_of_entry[e["entry_id"]] = rid
                if rid == record_id:
                    out.append({k: e.get(k) for k in ("entry_id", "op", "recorded_at", "recorded_by", "reason", "replaces", "section", "record")})
        return out

    def get_ir(self) -> dict[str, Any]:
        with self.lock:
            d = self.digest()
            if self._ir_cache and self._ir_cache[0] == d:
                return self._ir_cache[1]
            ir = self.engine.build_ir(self.dir, self.facts, self.judgments)
            self._ir_cache = (d, ir)
            return ir

    # ------------------------------------------------------------------ 書く
    def _next_entry_ids(self, which: str, n: int) -> list[str]:
        prefix = "fe" if which == "facts" else "je"
        top = 0
        for e in self.entries(which):
            m = _ENTRY_NUM.match(e.get("entry_id", ""))
            if m:
                top = max(top, int(m.group(2)))
        return [f"{prefix}-{top + i + 1:05d}" for i in range(n)]

    def write(self, which: str, items: list[dict[str, Any]], *, recorded_by_person: str, dry_run: bool = False) -> WriteOutcome:
        """items：{"op": add|correct|delete, "section", "record"?, "record_id"?（correct・delete の対象）, "reason"?}。

        写しで append と build-ir を通してから本物に置き換える。失敗は EngineError（problems つき）。
        """
        assert which in ("facts", "judgments")
        with self.lock:
            self.ensure()
            heads = self.heads(which)
            ids = self._next_entry_ids(which, len(items))
            recorded_at = dbm.now_iso()
            drafts = []
            for eid, it in zip(ids, items):
                d: dict[str, Any] = {
                    "entry_id": eid,
                    "recorded_at": recorded_at,
                    "recorded_by": {"person": recorded_by_person},
                    "op": it["op"],
                    "section": it["section"],
                }
                if it["op"] in ("correct", "delete"):
                    head = heads.get(it["record_id"])
                    if head is None or head["op"] == "delete":
                        raise EngineError("訂正・取消しの対象の記録がない（取り消し済みかもしれない）", code="no_such_record")
                    if not it.get("reason"):
                        raise EngineError("訂正・取消しには理由が要る", code="reason_required")
                    d["replaces"] = head["entry_id"]
                    d["reason"] = it["reason"]
                if it["op"] in ("add", "correct"):
                    d["record"] = it["record"]
                drafts.append(d)
            work = self.tmp_dir / f"w-{dbm.new_id('x', 6)}"
            work.mkdir(parents=True)
            try:
                tf, tj = work / "facts.jsonl", work / "judgments.jsonl"
                shutil.copyfile(self.facts, tf)
                shutil.copyfile(self.judgments, tj)
                target = tf if which == "facts" else tj
                self.engine.append(target, which, drafts, work)
                ir = self.engine.build_ir(self.dir, tf, tj)
                if dry_run:
                    return WriteOutcome([d["entry_id"] for d in drafts], ir)  # 確かめるだけ（提案の前の検査）
                # 写しが通ったので本物に置き換える（同じボリュームの中なので原子的）
                real = self.facts if which == "facts" else self.judgments
                os.replace(target, real)
            finally:
                shutil.rmtree(work, ignore_errors=True)
            self._ir_cache = (self.digest(), ir)
            return WriteOutcome([d["entry_id"] for d in drafts], ir)

    # ------------------------------------------------------------------ 証憑
    def store_evidence(self, data: bytes, ext: str) -> tuple[str, Path]:
        """原本を sha256 の名前で置く。同じ中身ならそのまま。読み取り専用にする（書き換えない）。"""
        self.ensure()
        sha = hashlib.sha256(data).hexdigest()
        path = self.evidence_dir / f"{sha}.{ext}"
        if not path.exists():
            tmp = self.tmp_dir / f"up-{sha}.part"
            tmp.write_bytes(data)
            os.replace(tmp, path)
            try:
                os.chmod(path, stat.S_IREAD)
            except OSError:
                pass
        return sha, path

    def evidence_path(self, sha: str, ext: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", sha) or not re.fullmatch(r"[a-z0-9]{1,8}", ext):
            raise ValueError("証憑の名前の形が違う")
        return self.evidence_dir / f"{sha}.{ext}"

    def verify_evidence(self, sha: str, ext: str) -> bool:
        """原本が書き換わっていないか（中身のハッシュが名前と同じか）。"""
        p = self.evidence_path(sha, ext)
        return p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == sha
