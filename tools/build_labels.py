"""記録の欄と選択肢の日本語名（tools/labels_vocab.json）を frontend/src/lib/labels_vocab.js に書き出す。

    .work/venvs/web/Scripts/python.exe -I -X utf8 tools/build_labels.py

okura-gov の版を上げたら、足りない名前を tools/check_labels.mjs で調べ、labels_vocab.json に足してから実行する。
画面に英字の欄名（システムの中の名前）を出さないため。
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY_OK = re.compile(r"^[A-Za-z0-9_]{1,80}$")


def clean(d):
    out = {}
    for k, v in sorted(d.items()):
        if not KEY_OK.match(k) or not isinstance(v, str):
            continue
        v = "".join(ch for ch in v if ord(ch) >= 32)[:40]
        if v:
            out[k] = v
    return out


def main():
    src = json.loads((ROOT / "tools" / "labels_vocab.json").read_text(encoding="utf-8-sig"))
    fields, enums = clean(src.get("fields", {})), clean(src.get("enums", {}))
    js = (
        "// 記録の欄と選択肢の日本語名（tools/build_labels.py が tools/labels_vocab.json から作る。手で直さない）\n"
        f"export const FIELD_VOCAB = {json.dumps(fields, ensure_ascii=False, indent=0)};\n"
        f"export const ENUM_VOCAB = {json.dumps(enums, ensure_ascii=False, indent=0)};\n"
    )
    (ROOT / "frontend" / "src" / "lib" / "labels_vocab.js").write_text(js, encoding="utf-8", newline="\n")
    print(f"fields {len(fields)}, enums {len(enums)}")


if __name__ == "__main__":
    main()
