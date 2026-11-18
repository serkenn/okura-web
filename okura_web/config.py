"""パスと設定。環境変数で上書きできる。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def _venv_python(name: str) -> Path:
    base = ROOT / ".work" / "venvs" / name
    if sys.platform == "win32":
        return base / "Scripts" / "python.exe"
    return base / "bin" / "python"


@dataclass(frozen=True)
class Config:
    root: Path
    okura_gov: Path
    data_dir: Path
    core_python: Path
    records_python: Path
    host: str
    port: int
    # 判定コアの1回の計算の時間の上限（秒）。家族全体で数十秒かかる
    evaluate_timeout: int = 900
    records_timeout: int = 120
    # アップロードの上限（記録層の証憑の上限 256 MiB より小さくする）
    max_upload_bytes: int = 25 * 2**20
    # 1回のリクエストの本体の上限（アップロード以外）
    max_json_bytes: int = 4 * 2**20
    session_hours: int = 24 * 14
    # パスキー（webauthn）の仮想環境の Python（tools/auth-requirements.txt。版とハッシュを固定）
    auth_python: Path = _venv_python("auth")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "okura-web.sqlite3"

    @property
    def bridge_dir(self) -> Path:
        return self.root / "okura_web" / "bridge"

    @property
    def web_dir(self) -> Path:
        """画面（Vite でビルドしたもの）。`npm ci --ignore-scripts && npm run build` で作る。"""
        return self.root / "frontend" / "dist"


def load_config(**overrides) -> Config:
    data_dir = Path(os.environ.get("OKURA_WEB_DATA", str(ROOT / "data"))).resolve()
    cfg: dict[str, Any] = dict(
        root=ROOT,
        okura_gov=Path(os.environ.get("OKURA_GOV_DIR", str(ROOT / "vendor" / "okura-gov"))).resolve(),
        data_dir=data_dir,
        core_python=Path(os.environ.get("OKURA_CORE_PYTHON", str(_venv_python("core")))),
        records_python=Path(os.environ.get("OKURA_RECORDS_PYTHON", str(_venv_python("records")))),
        host=os.environ.get("OKURA_WEB_HOST", "127.0.0.1"),
        port=int(os.environ.get("OKURA_WEB_PORT", "8765")),
    )
    cfg.update(overrides)
    return Config(**cfg)
