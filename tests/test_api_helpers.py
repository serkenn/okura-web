"""api.py の純粋な部品：sniff・_check_query・_in_year・filter_digest（サーバーは起動しない）。"""

from __future__ import annotations

import unittest

from okura_web import api
from okura_web import results as R
from okura_web.server import HttpError

from ._fixtures import SPLIT_INJECT, SPLIT_LIVELIHOOD, consent, make_access, raw_result


class SniffTest(unittest.TestCase):
    def test_known_formats(self) -> None:
        cases = {
            b"\xff\xd8\xff\xe0" + b"\0" * 16: ("jpg", "image/jpeg"),
            b"\x89PNG\r\n\x1a\n" + b"\0" * 8: ("png", "image/png"),
            b"GIF87a...": ("gif", "image/gif"),
            b"GIF89a...": ("gif", "image/gif"),
            b"%PDF-1.7\n": ("pdf", "application/pdf"),
            b"RIFF\x10\0\0\0WEBPVP8 ": ("webp", "image/webp"),
            b"\0\0\0\x18ftypheic\0\0\0\0": ("heic", "image/heic"),
            b"\0\0\0\x18ftypmif1\0\0\0\0": ("heic", "image/heic"),
        }
        for data, expected in cases.items():
            with self.subTest(data=data[:12]):
                self.assertEqual(api.sniff(data), expected)

    def test_unknown_or_lookalike(self) -> None:
        for data in (
            b"",
            b"<html><script>",
            b"RIFF\x10\0\0\0WAVEfmt ",  # RIFF でも WEBP でない
            b"\0\0\0\x18ftypisom\0\0\0\0",  # mp4
            b"PK\x03\x04",
            b" %PDF-1.7",  # 先頭でない
        ):
            with self.subTest(data=data[:12]):
                self.assertIsNone(api.sniff(data))


class CheckQueryTest(unittest.TestCase):
    def assertBad(self, q: object, code: str = "bad_query") -> None:
        with self.assertRaises(HttpError) as cm:
            api._check_query(q)
        self.assertEqual(cm.exception.status, 400)
        self.assertEqual(cm.exception.code, code)

    def test_defaults_and_scenarios_forced_empty(self) -> None:
        out = api._check_query({"income_tax_years": [2026], "scenarios": [{"id": "x"}], "unknown_key": 1})
        self.assertEqual(out["income_tax_years"], [2026])
        self.assertEqual(out["scenarios"], [])
        self.assertNotIn("unknown_key", out)
        self.assertEqual(out["resident_tax_fiscal_years"], [2026, 2027])

    def test_years(self) -> None:
        self.assertEqual(api._check_query({"kokunen_fiscal_years": [2000, 2100]})["kokunen_fiscal_years"], [2000, 2100])
        for bad in ([1999], [2101], [True], ["2026"], [2026.0], 2026, None):
            with self.subTest(bad=bad):
                self.assertBad({"income_tax_years": bad})
        self.assertBad([2026])  # 問いがオブジェクトでない

    def test_judgment_dates(self) -> None:
        self.assertBad({"dependent_judgment_dates": "2026-12-31"})
        self.assertBad({"dependent_judgment_dates": ["2026-02-30"]}, "bad_date")
        self.assertBad({"dependent_judgment_dates": ["2026/12/31"]}, "bad_date")
        self.assertBad({"dependent_judgment_dates": [20261231]}, "bad_date")
        out = api._check_query({"dependent_judgment_dates": ["2024-02-29"]})
        self.assertEqual(out["dependent_judgment_dates"], ["2024-02-29"])

    def test_filing_date(self) -> None:
        self.assertBad({"filing_date": "2027-03-15"})
        self.assertBad({"filing_date": {"on": "2027-02-29"}}, "bad_date")
        self.assertBad({"filing_date": {}}, "bad_date")
        out = api._check_query({"filing_date": {"on": "2027-03-15"}})
        self.assertEqual(out["filing_date"], {"on": "2027-03-15", "planned": True})
        out = api._check_query({"filing_date": {"on": "2027-03-15", "planned": 0}})
        self.assertIs(out["filing_date"]["planned"], False)
        self.assertIsNone(api._check_query({"filing_date": None})["filing_date"])


class InYearTest(unittest.TestCase):
    def test_shapes(self) -> None:
        self.assertTrue(api._in_year({"when": {"tax_year": 2026}}, 2026))
        self.assertFalse(api._in_year({"when": {"tax_year": 2025}}, 2026))
        self.assertTrue(api._in_year({"when": {"fiscal_year": 2027}}, 2026))  # 2026年の所得で決まる年度
        self.assertTrue(api._in_year({"when": {"fiscal_year": 2026}}, 2026))
        self.assertFalse(api._in_year({"when": {"fiscal_year": 2028}}, 2026))
        self.assertTrue(api._in_year({"when": {"on": "2026-07-01"}}, 2026))
        self.assertFalse(api._in_year({"when": {"on": "2025-12-31"}}, 2026))
        self.assertTrue(api._in_year({"when": {"from_on": "2020-04-01"}}, 2026))  # 終わりなし
        self.assertTrue(api._in_year({"when": {"from_on": "2025-04-01", "to_on": "2026-03-31"}}, 2026))
        self.assertFalse(api._in_year({"when": {"from_on": "2025-04-01", "to_on": "2025-12-31"}}, 2026))
        self.assertTrue(api._in_year({"id": "p-a", "birth_on": "1980-01-01"}, 2026))  # 時点のない記録


class FilterDigestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.d = R.digest(R.LoadedResult(raw_result()))

    def persons_everywhere(self, d: dict) -> set:
        found = {v["person"] for v in d["key_values"]}
        for q in d["questions"]:
            found |= set(q["persons"]) | {a["person"] for a in q["affects"]}
        for g in d["out_of_scope"]:
            found |= {v["person"] for v in g["values"]}
        for k in ("boundaries", "age_boundaries", "forms"):
            found |= {b["person"] for b in d[k]}
        found |= {w["person"] for w in d["filing"]["withheld"]}
        return found

    def test_hidden_person_removed_everywhere(self) -> None:
        acc = make_access("p-a")  # p-a 本人、p-c は管理する子、p-b は同意なし
        out = api.filter_digest(self.d, acc)
        self.assertEqual(out["persons"], ["p-a", "p-c"])
        self.assertEqual(out["hidden_persons"], ["p-b"])
        self.assertNotIn("p-b", self.persons_everywhere(out))
        self.assertEqual(out["out_of_scope"], [])  # p-b だけの群は群ごと消える
        q_inj = next(q for q in out["questions"] if q["id"] == SPLIT_INJECT["id"])
        self.assertEqual(q_inj["affects"], [])
        # 元の digest は書き換えない
        self.assertIn("p-b", self.persons_everywhere(self.d))

    def test_question_about_hidden_person_dropped(self) -> None:
        acc = make_access("p-b", managed=set())  # p-b は p-a・p-c の同意がない
        out = api.filter_digest(self.d, acc)
        self.assertEqual(out["persons"], ["p-b"])
        self.assertEqual(out["hidden_persons"], ["p-a", "p-c"])
        ids = [q["id"] for q in out["questions"]]
        self.assertNotIn(SPLIT_LIVELIHOOD["id"], ids)  # p-c についての判断
        self.assertEqual({v["id"] for v in out["key_values"]}, {"v-4", "v-6"})
        self.assertEqual([f["person"] for f in out["forms"]], ["p-b"])

    def test_consent_makes_numbers_visible(self) -> None:
        acc = make_access("p-a", consents={("p-b", "share_numbers"): consent(1)})
        out = api.filter_digest(self.d, acc)
        self.assertEqual(out["hidden_persons"], [])
        self.assertEqual(len(out["key_values"]), len(self.d["key_values"]))
        acc = make_access("p-a", consents={("p-b", "share_details"): consent(1)})
        self.assertEqual(api.filter_digest(self.d, acc)["hidden_persons"], ["p-b"])


if __name__ == "__main__":
    unittest.main()
