"""okura-gov との窓口：記録層（records）と判定コア（core）を別の仮想環境のサブプロセスとして起動する。

- Web のサーバーは okura_core・okura_records を import しない（AGPL・GPL のコードを同じプロセスに入れない。SCOPE §6-2）。
- Python は必ず `-I -X utf8` で起動する（-I：カレントディレクトリやスクリプトのディレクトリの .py を読まない。
  -X utf8：Windows の cp932 では日本語の YAML を読めない）。
- やり取りは JSON だけ。サブプロセスの標準エラー出力（家族のデータを含みうる）はログに書かない。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Config


class EngineError(Exception):
    """サブプロセスの起動や出力の誤り。message は利用者に見せてよい文（家族のデータを含めない）。"""

    def __init__(self, message: str, *, code: str = "engine_error", problems: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.code = code
        self.problems = problems or []


@dataclass
class RunResult:
    returncode: int
    stdout: bytes
    stderr: bytes = field(repr=False)


def _clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTHON")}
    env["PYTHONIOENCODING"] = "utf-8"  # -I では読まれないが、子の子（spawn のワーカー）のために残す
    return env


class Engine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._meta_lock = threading.Lock()
        self._meta: dict[str, Any] | None = None
        self.cwd = cfg.data_dir / "tmp" / "cwd"
        self.cwd.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ 起動
    def _run(self, python: Path, args: list[str], *, stdin: bytes | None = None, timeout: int) -> RunResult:
        if not python.exists():
            raise EngineError(
                f"仮想環境の Python が見つからない（{python.name}）。README の「仮想環境の作り方」で作る",
                code="venv_missing",
            )
        cmd = [str(python), "-I", "-X", "utf8", *args]
        kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            p = subprocess.run(
                cmd,
                input=stdin,
                capture_output=True,
                timeout=timeout,
                cwd=str(self.cwd),
                env=_clean_env(),
                check=False,
                **kwargs,
            )
        except subprocess.TimeoutExpired as e:
            raise EngineError(f"計算が {timeout} 秒で終わらなかった", code="timeout") from e
        return RunResult(p.returncode, p.stdout, p.stderr)

    def records(self, args: list[str], *, stdin: bytes | None = None) -> RunResult:
        return self._run(self.cfg.records_python, ["-m", "okura_records.cli", *args], stdin=stdin, timeout=self.cfg.records_timeout)

    # ------------------------------------------------------------------ 版
    def okura_gov_version(self) -> dict[str, Any]:
        """固定している okura-gov の版（サブモジュールのコミット）。git を呼ぶので 30 秒は覚えておく。"""
        import time

        cached = getattr(self, "_ver_cache", None)
        if cached and time.monotonic() - cached[0] < 30:
            return dict(cached[1])
        v = self._okura_gov_version()
        self._ver_cache = (time.monotonic(), v)
        return dict(v)

    def _okura_gov_version(self) -> dict[str, Any]:
        head = None
        dirty = None
        try:
            p = subprocess.run(
                ["git", "-C", str(self.cfg.okura_gov), "rev-parse", "HEAD"], capture_output=True, timeout=10, check=False
            )
            if p.returncode == 0:
                head = p.stdout.decode().strip()
            p2 = subprocess.run(
                ["git", "-C", str(self.cfg.okura_gov), "status", "--porcelain"], capture_output=True, timeout=10, check=False
            )
            if p2.returncode == 0:
                dirty = bool(p2.stdout.strip())
        except (OSError, subprocess.TimeoutExpired):
            pass
        pinned = None
        try:
            p3 = subprocess.run(
                ["git", "-C", str(self.cfg.root), "ls-files", "--stage", "vendor/okura-gov"], capture_output=True, timeout=10, check=False
            )
            if p3.returncode == 0 and p3.stdout:
                pinned = p3.stdout.decode().split()[1]  # 「160000 <コミット> 0	vendor/okura-gov」（サブモジュールの固定）
        except (OSError, subprocess.TimeoutExpired, IndexError):
            pass
        return {
            "commit": head,
            "short": head[:7] if head else None,
            "pinned_commit": pinned,
            "matches_pin": (pinned is None or head == pinned) if head else None,
            "locally_modified": dirty,
            "path": "vendor/okura-gov",
        }

    # ------------------------------------------------------------------ 語彙・注入点
    def meta(self) -> dict[str, Any]:
        with self._meta_lock:
            if self._meta is None:
                r1 = self._run(self.cfg.records_python, [str(self.cfg.bridge_dir / "meta_records.py")], timeout=120)
                r2 = self._run(self.cfg.core_python, [str(self.cfg.bridge_dir / "meta_core.py")], timeout=300)
                if r1.returncode != 0 or r2.returncode != 0:
                    raise EngineError("okura-gov の語彙・注入点を読めなかった", code="meta_failed")
                meta = json.loads(r1.stdout.decode("utf-8"))
                meta.update(json.loads(r2.stdout.decode("utf-8")))
                meta["okura_gov"] = self.okura_gov_version()
                self._meta = meta
            return self._meta

    # ------------------------------------------------------------------ 記録層
    def build_ir(self, ledger_dir: Path, facts: Path, judgments: Path) -> dict[str, Any]:
        """中間表現を作る。問題があれば EngineError（problems に where・code・message）。"""
        r = self.records(
            [
                "build-ir",
                "--ledger", str(ledger_dir / "main.beancount"),
                "--facts", str(facts),
                "--judgments", str(judgments),
                "--root", str(ledger_dir),
            ]
        )
        if r.returncode == 0:
            return json.loads(r.stdout.decode("utf-8"))
        problems = _problems(r.stderr)
        if r.returncode == 1:
            raise EngineError("データベースの記録から計算の入力を作れなかった（入力の問題）", code="ir_problems", problems=problems)
        raise EngineError("記録層の起動に失敗した", code="records_failed", problems=problems)

    def append(self, ledger_file: Path, which: str, drafts: list[dict[str, Any]], tmp_dir: Path) -> None:
        """事実台帳・判断台帳に下書きを足す（prev_sha256 は記録層が入れる。台帳全体を検査してから書く）。"""
        assert which in ("facts", "judgments")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        draft_path = tmp_dir / f"draft-{os.getpid()}-{threading.get_ident()}.json"
        draft_path.write_bytes(json.dumps(drafts, ensure_ascii=False).encode("utf-8"))
        try:
            r = self.records(["append", f"--{which}", str(ledger_file), "--draft", str(draft_path)])
        finally:
            try:
                draft_path.unlink()
            except OSError:
                pass
        if r.returncode != 0:
            raise EngineError("データベースに書けなかった", code="append_failed", problems=_problems(r.stderr))

    def transactions(self, ledger_dir: Path) -> dict[str, Any]:
        r = self.records(["transactions", "--ledger", str(ledger_dir / "main.beancount"), "--root", str(ledger_dir)])
        if r.returncode != 0:
            raise EngineError("データベース（beancount）を読めなかった", code="ledger_problems", problems=_problems(r.stderr))
        return json.loads(r.stdout.decode("utf-8"))

    def transactions_file(self, ledger: Path, root: Path) -> dict[str, Any]:
        """任意の beancount の台帳（家計簿の写しなど）を記録層の安全な読み込みで確かめて、正規化した取引 JSON にする。"""
        r = self.records(["transactions", "--ledger", str(ledger), "--root", str(root)])
        if r.returncode != 0:
            raise EngineError("データベース（beancount）を読めなかった", code="ledger_problems", problems=_problems(r.stderr))
        return json.loads(r.stdout.decode("utf-8"))

    # ------------------------------------------------------------------ 判定コア
    def evaluate(self, ir: dict[str, Any], query: dict[str, Any], injected: list[dict[str, Any]] | None) -> bytes:
        """判定コアのコマンド（標準入力 {ir, query, injected} → 標準出力の結果 JSON）。結果のバイト列を返す。"""
        payload = json.dumps({"ir": ir, "query": query, "injected": injected}, ensure_ascii=False).encode("utf-8")
        r = self._run(self.cfg.core_python, ["-m", "okura_core.cli"], stdin=payload, timeout=self.cfg.evaluate_timeout)
        if r.returncode == 0:
            return r.stdout
        if r.returncode == 2:
            try:
                errs = json.loads(r.stdout.decode("utf-8")).get("errors", [])
            except (ValueError, UnicodeDecodeError):
                errs = []
            raise EngineError("判定コアが入力を受け付けなかった", code="evaluate_input", problems=errs)
        if r.returncode == 4:
            raise EngineError("判定コアの起動のしかたの誤り（-I と -X utf8）", code="evaluate_launch")
        raise EngineError("判定コアの内部の誤り（okura-gov 側で直す。AGENTS.md の手順）", code="evaluate_internal")

    def check_injected(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        r = self._run(
            self.cfg.core_python,
            [str(self.cfg.bridge_dir / "check_injected.py")],
            stdin=json.dumps(entries, ensure_ascii=False).encode("utf-8"),
            timeout=300,
        )
        if r.returncode != 0:
            raise EngineError("注入データの検査を起動できなかった", code="check_failed")
        return json.loads(r.stdout.decode("utf-8")).get("problems", [])


def _problems(stderr: bytes) -> list[dict[str, Any]]:
    """記録層の標準エラー出力 {"ok": false, "problems": [...]} を取り出す。形が違えば空（生の出力はログにも返さない）。"""
    try:
        data = json.loads(stderr.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return []
    probs = data.get("problems") if isinstance(data, dict) else None
    if not isinstance(probs, list):
        return []
    out = []
    for p in probs[:200]:
        if isinstance(p, dict):
            item = {k: p.get(k) for k in ("where", "code", "message", "origin") if k in p}
            for k in ("where", "origin"):
                if isinstance(item.get(k), str):
                    item[k] = _strip_dirs(item[k])
            out.append(item)
    return out


def _strip_dirs(s: str) -> str:
    """問題の場所から絶対パス（作業用のディレクトリ）を除き、ファイル名だけにする。"""
    import re

    return re.sub(r"(?:[A-Za-z]:)?(?:[\\/][^\\/:*?\"<>|\r\n]+)*[\\/]([^\\/]+\.(?:jsonl|beancount))", r"\1", s)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
