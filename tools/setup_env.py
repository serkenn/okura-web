"""仮想環境を作る（okura-gov の AGENTS.md「仮想環境の作り方」に従う。標準ライブラリだけ）。

    uv run --no-project --python 3.11 python -I -X utf8 tools/setup_env.py

- 判定コア（core：openfisca-core、AGPL）と記録層（records：beancount、GPL）は別々の仮想環境。wheel だけを入れる（--only-binary :all:）。
- okura-gov の自作のパッケージは pip で入れず、okura_dev.pth に vendor/okura-gov の src の絶対パスを書く（固定した版を使う）。
- Web のサーバー（web）は標準ライブラリだけの仮想環境。
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOV = ROOT / "vendor" / "okura-gov"
VENVS = ROOT / ".work" / "venvs"


def py(name: str) -> Path:
    return VENVS / name / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def site(name: str) -> Path:
    if sys.platform == "win32":
        return VENVS / name / "Lib" / "site-packages"
    return next((VENVS / name / "lib").glob("python3.*/site-packages"))


def run(*cmd: str) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    if not (GOV / "packages" / "core").exists():
        print("vendor/okura-gov がない。git submodule update --init を先に", file=sys.stderr)
        return 2
    for name in ("core", "records", "web", "auth"):
        if not py(name).exists():
            run("uv", "venv", str(VENVS / name), "--python", "3.11")
    run("uv", "pip", "install", "--python", str(py("core")), "--only-binary", ":all:", "openfisca-core==46.0.1")
    run("uv", "pip", "install", "--python", str(py("records")), "--only-binary", ":all:", "beancount==3.2.3", "beanquery==0.2.0")
    # パスキー：版とハッシュを固定し、wheel だけ・依存の解決をしない（tools/auth-requirements.txt）
    run("uv", "pip", "install", "--python", str(py("auth")), "--require-hashes", "--only-binary", ":all:", "--no-deps",
        "-r", str(ROOT / "tools" / "auth-requirements.txt"))
    g = GOV.resolve().as_posix()
    (site("core") / "okura_dev.pth").write_text(f"{g}/packages/ir/src\n{g}/packages/core/src\n", encoding="utf-8")
    (site("records") / "okura_dev.pth").write_text(f"{g}/packages/ir/src\n{g}/packages/records/src\n", encoding="utf-8")
    run(str(py("core")), "-I", "-X", "utf8", "-c", "import okura_core, okura_ir; print('core ok')")
    run(str(py("records")), "-I", "-X", "utf8", "-c", "import okura_records; print('records ok')")
    run(str(py("auth")), "-I", "-X", "utf8", "-c", "import webauthn; print('auth ok')")
    print("できた。起動：", py("web"), "-I -X utf8 serve.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
