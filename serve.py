"""okura-web を起動する。

    .work/venvs/web/Scripts/python.exe -I -X utf8 serve.py

-I（隔離モード）ではスクリプトのディレクトリが sys.path に入らないので、ここで明示的にリポジトリの根だけを足す。
okura_core・okura_records はこのプロセスに入れない（サブプロセスで呼ぶ）。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from okura_web.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
