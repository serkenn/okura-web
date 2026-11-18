"""総務省の「全国地方公共団体コード」の Excel から、市区町村を名前で選ぶための一覧 frontend/src/lib/municipalities.js を作る。

    .work/venvs/web/Scripts/python.exe -I -X utf8 tools/build_municipalities.py <ダウンロードした .xlsx>

入手元：https://www.soumu.go.jp/denshijiti/code.html（都道府県コード及び市区町村コード）。
標準ライブラリだけで読む（zip と XML）。取り出すのは 6 桁のコード・都道府県名・市区町村名・読みだけで、形を検査してから書く。
"""

import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
CODE_OK = re.compile(r"^\d{6}$")
MAX_XML = 50 * 1024 * 1024


def read_xml(z: zipfile.ZipFile, name: str) -> ET.Element:
    info = z.getinfo(name)
    if info.file_size > MAX_XML:
        raise SystemExit(f"{name} が大きすぎる")
    data = z.read(name)
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise SystemExit("DTD・実体の定義を含む XML は読まない")
    return ET.fromstring(data)


def col_index(ref: str) -> int:
    m = re.match(r"[A-Z]+", ref)
    letters = m.group(0) if m else "A"
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def rows(path: Path):
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in read_xml(z, "xl/sharedStrings.xml").findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        sheet = read_xml(z, "xl/worksheets/sheet1.xml")
        for row in sheet.iter(f"{{{NS['m']}}}row"):
            out = {}
            for c in row.findall("m:c", NS):
                v = c.find("m:v", NS)
                if v is None or v.text is None:
                    is_ = c.find("m:is", NS)
                    text = "".join(t.text or "" for t in is_.iter(f"{{{NS['m']}}}t")) if is_ is not None else ""
                elif c.get("t") == "s":
                    text = shared[int(v.text)]
                else:
                    text = v.text
                out[col_index(c.get("r") or "A1")] = text.strip()
            yield [out.get(i, "") for i in range(max(out) + 1)] if out else []


def clean(s: str, n: int) -> str:
    return "".join(ch for ch in s if ord(ch) >= 32)[:n]


def main(src: str) -> None:
    items = []
    for r in rows(Path(src)):
        if len(r) < 3:
            continue
        code = r[0].split(".")[0]
        if not CODE_OK.match(code):
            continue
        pref, name = clean(r[1], 10), clean(r[2], 20)
        kana = clean(r[4] if len(r) > 4 else "", 40)
        if not name:  # 都道府県の行（市区町村名なし）は除く
            continue
        items.append([code, pref, name, kana])
    if len(items) < 1500:
        raise SystemExit(f"市区町村が少なすぎる（{len(items)}）。表の形が変わったかもしれない")
    js = (
        "// 市区町村コード（総務省「全国地方公共団体コード」。tools/build_municipalities.py が作る。手で直さない）\n"
        "// [6桁のコード, 都道府県, 市区町村, 読み]\n"
        f"export const MUNICIPALITIES = {json.dumps(items, ensure_ascii=False, separators=(',', ':'))};\n"
    )
    (ROOT / "frontend" / "src" / "lib" / "municipalities.js").write_text(js, encoding="utf-8", newline="\n")
    print(f"{len(items)} municipalities")


if __name__ == "__main__":
    main(sys.argv[1])
