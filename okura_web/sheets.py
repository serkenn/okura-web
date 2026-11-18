"""表のファイル（Excel の .xlsx・CSV・TSV・テキスト）を、AI に渡す文字の表にする（標準ライブラリだけ）。

- .xlsx は zip の中の XML を読むだけ。マクロ（.xlsm の VBA）・外部リンク・数式は実行しない（保存されている値だけ）。
- 信頼できないファイルとして扱う：zip の中の大きさ・ファイル数の上限、展開後の大きさの上限、DTD・実体の定義を含む XML は読まない。
- 出力は「シートごとのタブ区切りの表」。行と列の上限で切り、切ったことを書く。
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MAX_XML = 40 * 2**20
MAX_TOTAL = 120 * 2**20
MAX_ENTRIES = 2000
MAX_ROWS = 400
MAX_COLS = 40
MAX_CHARS = 60000
MAX_SHEETS = 5


class SheetError(Exception):
    pass


def _xml(z: zipfile.ZipFile, name: str) -> ET.Element:
    info = z.getinfo(name)
    if info.file_size > MAX_XML:
        raise SheetError("表の中身が大きすぎる")
    data = z.read(name)
    head = data[:4096]
    if b"<!DOCTYPE" in head or b"<!ENTITY" in data:
        raise SheetError("表の形が変（DTD・実体の定義）")
    return ET.fromstring(data)


def _col(ref: str) -> int:
    m = re.match(r"[A-Z]+", ref or "A")
    n = 0
    for ch in (m.group(0) if m else "A"):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _cell_text(c: ET.Element, shared: list[str]) -> str:
    t = c.get("t")
    v = c.find("m:v", NS)
    if t == "inlineStr":
        is_ = c.find("m:is", NS)
        return "".join(x.text or "" for x in is_.iter(f"{{{NS['m']}}}t")) if is_ is not None else ""
    if v is None or v.text is None:
        return ""
    if t == "s":
        try:
            return shared[int(v.text)]
        except (ValueError, IndexError):
            return ""
    if t == "b":
        return "TRUE" if v.text == "1" else "FALSE"
    return v.text


def xlsx_tables(data: bytes) -> list[tuple[str, list[list[str]]]]:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise SheetError("Excel のファイルとして読めない") from e
    with z:
        infos = z.infolist()
        if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_TOTAL:
            raise SheetError("Excel のファイルが大きすぎる")
        names = set(z.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for si in _xml(z, "xl/sharedStrings.xml").findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        sheets: list[tuple[str, str]] = []
        if "xl/workbook.xml" in names and "xl/_rels/workbook.xml.rels" in names:
            rels = {r.get("Id"): r.get("Target") for r in _xml(z, "xl/_rels/workbook.xml.rels")}
            for s in _xml(z, "xl/workbook.xml").iter(f"{{{NS['m']}}}sheet"):
                target = rels.get(s.get(f"{{{RNS}}}id")) or ""
                path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
                if path in names:
                    sheets.append((s.get("name") or "シート", path))
        if not sheets:
            sheets = [(n.rsplit("/", 1)[-1], n) for n in sorted(names) if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
        out = []
        for title, path in sheets[:MAX_SHEETS]:
            rows: list[list[str]] = []
            for row in _xml(z, path).iter(f"{{{NS['m']}}}row"):
                cells: dict[int, str] = {}
                for c in row.findall("m:c", NS):
                    i = _col(c.get("r") or "A")
                    if i < MAX_COLS:
                        cells[i] = _cell_text(c, shared).strip()
                if any(cells.values()):
                    rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
                if len(rows) > MAX_ROWS:
                    break
            out.append((title, rows))
        return out


def text_table(data: bytes) -> list[list[str]]:
    for enc in ("utf-8-sig", "cp932"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SheetError("文字コードを読めない（UTF-8 か Shift_JIS）")
    if "\x00" in text:
        raise SheetError("文字のファイルではない")
    sample = text[:4096]
    delim = "\t" if sample.count("\t") > sample.count(",") else ","
    rows = []
    for r in csv.reader(io.StringIO(text), delimiter=delim):
        if any(x.strip() for x in r):
            rows.append([x.strip() for x in r[:MAX_COLS]])
        if len(rows) > MAX_ROWS:
            break
    return rows


def to_text(name: str, tables: list[tuple[str, list[list[str]]]]) -> str:
    """AI に渡す文字：シートごとにタブ区切り。上限で切ったら書く。"""
    parts = []
    for title, rows in tables:
        cut = len(rows) > MAX_ROWS
        body = "\n".join("\t".join(c.replace("\t", " ").replace("\n", " ") for c in r) for r in rows[:MAX_ROWS])
        parts.append(f"## シート：{title}（{min(len(rows), MAX_ROWS)}行{'。ここで切った' if cut else ''}）\n{body}")
    text = f"# 添付の表：{name}\n" + "\n\n".join(parts)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n…（長いので、ここで切った）"
    return text


def read_table(name: str, ext: str, data: bytes) -> str:
    if ext == "xlsx":
        return to_text(name, xlsx_tables(data))
    return to_text(name, [("表", text_table(data))])


def summarize(tables: list[tuple[str, list[list[str]]]]) -> dict[str, Any]:
    return {"sheets": [{"name": t, "rows": len(r)} for t, r in tables]}
