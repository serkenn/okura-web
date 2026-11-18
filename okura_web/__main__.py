"""起動：.work/venvs/web/Scripts/python.exe -I -X utf8 -m okura_web [--host 127.0.0.1] [--port 8765] [--allow-host 192.168.1.10:8765]

-I で起動するので、リポジトリの根をカレントディレクトリにして `-m okura_web` では読めない。serve.py を使う（README）。
"""

from __future__ import annotations

import argparse
import sys

from . import api, api_agent, api_book, api_invite, api_passkey  # noqa: F401 - 経路を登録する
from .app import App
from .config import load_config
from .server import Server


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="okura-web")
    ap.add_argument("--host")
    ap.add_argument("--port", type=int)
    ap.add_argument("--allow-host", action="append", default=[], help="LAN から使うときのホスト名:ポート（Host ヘッダーの許可）")
    ap.add_argument("--public-host", action="append", default=[], help="Cloudflare トンネルで公開するホスト名（Cloudflare Access の JWT を必ず確かめる）")
    a = ap.parse_args(argv)
    if not sys.flags.isolated:
        sys.stderr.write("okura-web は python -I で起動する（README）\n")
        return 2
    over = {}
    if a.host:
        over["host"] = a.host
    if a.port:
        over["port"] = a.port
    cfg = load_config(**over)
    app = App(cfg)
    api.APP = app
    srv = Server(app, api.router, allowed_hosts=set(a.allow_host), public_hosts=set(a.public_host))
    sys.stderr.write(f"okura-web: http://{cfg.host}:{cfg.port}/  （データ：{cfg.data_dir}）\n")
    if cfg.host not in ("127.0.0.1", "localhost", "::1"):
        sys.stderr.write("注意：127.0.0.1 以外で待ち受けている。HTTP は暗号化されない。家族の LAN の中だけで使う\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
