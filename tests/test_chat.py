"""AI の会話の部品：表のファイルの読み取り（sheets）・記録の形の直し・カードの作り方・保存した会話の送り方。架空のデータだけ。"""

from __future__ import annotations

import io
import unittest
import zipfile

from okura_web import agent, sheets
from okura_web.tools import normalize_record

_CT = '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
_WB = ('<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="明細" sheetId="1" r:id="rId1"/></sheets></workbook>')
_RELS = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         '<Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
_SST = '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>日付</t></si><si><t>架空スーパー</t></si></sst>'
_SHEET = ('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
          '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="inlineStr"><is><t>金額</t></is></c></row>'
          '<row r="2"><c r="A2"><v>46327</v></c><c r="B2"><v>3200</v></c><c r="C2" t="s"><v>1</v></c></row>'
          '</sheetData></worksheet>')


def xlsx(sheet: str = _SHEET) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("xl/workbook.xml", _WB)
        z.writestr("xl/_rels/workbook.xml.rels", _RELS)
        z.writestr("xl/sharedStrings.xml", _SST)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


class SheetsTest(unittest.TestCase):
    def test_xlsx_values_and_sheet_name(self) -> None:
        text = sheets.read_table("架空の明細.xlsx", "xlsx", xlsx())
        self.assertIn("シート：明細", text)
        self.assertIn("日付\t金額", text)
        self.assertIn("46327\t3200\t架空スーパー", text)

    def test_xlsx_rejects_dtd_and_bad_zip(self) -> None:
        bad = _SHEET.replace('<?xml version="1.0"?>', '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]>')
        with self.assertRaises(sheets.SheetError):
            sheets.read_table("x.xlsx", "xlsx", xlsx(bad))
        with self.assertRaises(sheets.SheetError):
            sheets.read_table("x.xlsx", "xlsx", b"PK\x03\x04 not really a zip")

    def test_csv_utf8_and_sjis_and_tsv(self) -> None:
        csv_text = "日付,摘要,出金\n2026/11/01,架空スーパー,3200\n"
        self.assertIn("架空スーパー\t3200", sheets.read_table("a.csv", "csv", csv_text.encode("utf-8")))
        self.assertIn("架空スーパー\t3200", sheets.read_table("a.csv", "csv", csv_text.encode("cp932")))
        self.assertIn("架空スーパー\t3200", sheets.read_table("a.tsv", "tsv", csv_text.replace(",", "\t").encode("utf-8")))
        with self.assertRaises(sheets.SheetError):
            sheets.read_table("a.csv", "csv", b"a\x00b")

    def test_rows_are_capped(self) -> None:
        many = "\n".join(f"{i},架空" for i in range(sheets.MAX_ROWS + 50)).encode()
        text = sheets.read_table("a.csv", "csv", many)
        self.assertIn("ここで切った", text)


class AgentPartsTest(unittest.TestCase):
    def test_normalize_moves_dates_into_when(self) -> None:
        rec = normalize_record({"kind": "medical_payment", "on": "2026-11-03", "id": "x", "recorded_at": "y", "when": {"on": "2026-11-04"}})
        self.assertEqual(rec["when"], {"on": "2026-11-04"})  # when にあればそちらを残す
        self.assertNotIn("id", rec)
        self.assertEqual(normalize_record({"kind": "k", "from_on": "2026-01-01", "to_on": "2026-12-31"})["when"], {"from_on": "2026-01-01", "to_on": "2026-12-31"})

    def test_ui_blocks_from_tool_results(self) -> None:
        self.assertEqual(agent._ui_from("propose_record", {"proposal_id": "pr-1"}), {"type": "proposals", "ids": ["pr-1"]})
        self.assertEqual(agent._ui_from("propose_records", {"proposal_ids": ["pr-1", "pr-2"]}), {"type": "proposals", "ids": ["pr-1", "pr-2"]})
        self.assertEqual(agent._ui_from("ask_user", {"asked": True, "question": "架空の質問", "options": ["はい", "いいえ"]})["type"], "choices")
        self.assertEqual(agent._ui_from("propose_book_entries", {"batch_id": "imp-1", "accepted": 3})["count"], 3)
        self.assertIsNone(agent._ui_from("propose_record", {"error": "x"}))
        self.assertIsNone(agent._ui_from("list_records", {"records": []}))

    def test_sanitize_drops_ui_and_mentions_attachments(self) -> None:
        m = agent._sanitize({"role": "assistant", "content": "ok", "ui": [{"type": "proposals"}]})
        self.assertEqual(m, {"role": "assistant", "content": "ok"})
        u = agent._sanitize({"role": "user", "content": "読んで", "attachments": [{"name": "架空.pdf"}]})
        self.assertIn("架空.pdf", u["content"])
        self.assertNotIn("attachments", u)


if __name__ == "__main__":
    unittest.main()
