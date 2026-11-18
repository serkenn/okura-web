"""ログインできなくなった人のパスワードを、このパソコンの上で付け替える。

使い方（リポジトリの根で）：
    .work/venvs/web/Scripts/python.exe -I -X utf8 tools/reset_password.py <ログイン名>

新しい仮のパスワード（ランダム）を作って1回だけ表示する。その人の今のログイン（セッション）はすべて切る。
ログインしたら、設定 → ログイン で自分のパスワードに変える。
このパソコンのデータベースを直接書き換えるので、使えるのはこのパソコンに入れる人（管理者）だけ。
"""
from __future__ import annotations

import secrets
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from okura_web.auth import hash_password  # noqa: E402
from okura_web.config import load_config  # noqa: E402

# 読み間違えやすい字（0 O 1 l I）を除く
ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        sys.stderr.write(__doc__ or "")
        return 2
    login = argv[0]
    db = sqlite3.connect(load_config().db_path)
    try:
        row = db.execute("SELECT id FROM users WHERE login=?", (login,)).fetchone()
        if row is None:
            sys.stderr.write("そのログイン名の人はいない\n")
            return 1
        password = "-".join("".join(secrets.choice(ALPHABET) for _ in range(5)) for _ in range(4))
        with db:
            db.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_password(password), row[0]))
            n = db.execute("DELETE FROM sessions WHERE user_id=?", (row[0],)).rowcount
        print(f"新しい仮のパスワード：{password}")
        print(f"切ったログイン：{n} 件。ログインしたら 設定 → ログイン で変えること")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
