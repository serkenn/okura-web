"""判定コアの仮想環境で動かす：注入データ（標準入力の JSON 配列）を判定コアの検査（parse_injected）に通し、問題を標準出力に書く。

起動：<core の python> -I -X utf8 check_injected.py < injected.json
"""

import json
import sys

from okura_core.injection import parse_injected


def main() -> int:
    raw = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    _, problems = parse_injected(raw)
    out = {"ok": not problems, "problems": [{"path": p.path, "code": p.code, "message": p.message} for p in problems]}
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
