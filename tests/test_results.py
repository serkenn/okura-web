"""結果のまとめ（results.py）：値の表示・時点・digest・判断の下書き。"""

from __future__ import annotations

import unittest

from okura_web import results as R

from ._fixtures import META, SPLIT_INJECT, SPLIT_LIVELIHOOD, raw_result


class FormatValueTest(unittest.TestCase):
    def test_yen_and_yen_range_without_rounding(self) -> None:
        self.assertEqual(R.format_value({"type": "yen", "amount": 1_234_567}), "1,234,567円")
        self.assertEqual(R.format_value({"type": "yen", "amount": 0}), "0円")
        # 幅は幅のまま（両端を丸めない・1つの値にまとめない）
        s = R.format_value({"type": "yen_range", "min": 100_001, "max": 100_999})
        self.assertEqual(s, "100,001円〜100,999円（幅）")

    def test_other_types_empty_and_unknown(self) -> None:
        self.assertEqual(R.format_value({"type": "bool", "value": True}), "はい")
        self.assertEqual(R.format_value({"type": "bool", "value": False}), "いいえ")
        self.assertEqual(R.format_value({"type": "integer", "value": 0}), "0")
        self.assertEqual(R.format_value({"type": "category", "value": "7割軽減"}), "7割軽減")
        self.assertEqual(R.format_value({"type": "date", "on": "2026-12-31"}), "2026-12-31")
        self.assertIsNone(R.format_value(None))
        self.assertIsNone(R.format_value({}))
        self.assertEqual(R.format_value({"type": "架空", "x": 1}), '{"type": "架空", "x": 1}')


class TimeTest(unittest.TestCase):
    def test_time_key_label_and_wareki(self) -> None:
        self.assertEqual(R.time_key({"tax_year": 2026}), "Y2026")
        self.assertEqual(R.time_key({"fiscal_year": 2027}), "FY2027")
        self.assertEqual(R.time_key({"on": "2026-12-31"}), "D2026-12-31")
        self.assertEqual(R.time_key({"b": 1, "a": 2}), '{"a": 2, "b": 1}')
        self.assertEqual(R.time_label({"tax_year": 2026}), "令和8年分（2026年の所得）")
        self.assertEqual(R.time_label({"fiscal_year": 2019}), "令和1年度（2019年度）")
        self.assertEqual(R.time_label({"on": "2026-01-01"}), "判定日 2026-01-01")
        self.assertEqual(R.wareki(2018), "2018年")


class DigestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.lr = R.LoadedResult(raw_result())
        self.d = R.digest(self.lr, okura_gov={"commit": "test"})

    def test_top_level(self) -> None:
        d = self.d
        self.assertTrue(d["ok"])
        self.assertEqual(d["versions"], {"core": "0.0-test", "okura_gov": {"commit": "test"}})
        self.assertEqual(d["query"], {"income_tax_years": [2026]})
        self.assertEqual(d["persons"], ["p-a", "p-b", "p-c"])
        self.assertEqual(d["counts"], {"values": 7, "undetermined": 3, "out_of_scope": 1})
        self.assertEqual(d["scenarios"], [{"id": "base", "label": "今の記録", "differences": 0}, {"id": "alt", "label": "架空の別案", "differences": 2}])

    def test_times_tax_year_first_with_institutions(self) -> None:
        keys = [t["key"] for t in self.d["times"]]
        self.assertEqual(keys, ["Y2026", "D2026-12-31", "FY2027"])
        by = {t["key"]: t for t in self.d["times"]}
        self.assertEqual(by["Y2026"]["institutions"], ["所得税"])
        self.assertEqual(by["FY2027"]["institutions"], ["住民税", "国保"])
        self.assertEqual(by["FY2027"]["label"], "令和9年度（2027年度）")

    def test_key_values_only_key_concepts(self) -> None:
        ids = [v["id"] for v in self.d["key_values"]]
        self.assertNotIn("v-5", ids)  # 主な値でない概念
        self.assertEqual(set(ids), {"v-1", "v-2", "v-3", "v-4", "v-6", "v-7"})
        v4 = next(v for v in self.d["key_values"] if v["id"] == "v-4")
        self.assertEqual(v4["value"], {"type": "yen_range", "min": 100_000, "max": 100_999})
        self.assertEqual(v4["display"], "100,000円〜100,999円（幅）")
        v3 = next(v for v in self.d["key_values"] if v["id"] == "v-3")
        self.assertIsNone(v3["display"])
        self.assertEqual(v3["undetermined"]["split_ids"], ["s-seikei-p-c"])
        self.assertTrue(v3["undetermined"]["evaluated"])
        self.assertCountEqual(v3["undetermined"]["candidate_values"], [{"type": "yen", "amount": 0}, {"type": "yen", "amount": 380_000}])
        v6 = next(v for v in self.d["key_values"] if v["id"] == "v-6")
        self.assertFalse(v6["undetermined"]["evaluated"])

    def test_questions_aggregated_per_split(self) -> None:
        qs = self.d["questions"]
        self.assertEqual([q["id"] for q in qs], [SPLIT_LIVELIHOOD["id"], SPLIT_INJECT["id"]])  # 判断 → 注入 の順
        q = qs[0]
        self.assertEqual(q["means"], "判断")
        self.assertTrue(q["means_help"])
        self.assertEqual(q["kind"], "判断.生計を一にするか")
        self.assertEqual(q["persons"], ["p-c"])
        self.assertEqual(q["candidates"], ["true", "false"])
        self.assertEqual(q["affects_count"], 2)
        per = {a["value_id"]: a["per_candidate"] for a in q["affects"]}
        self.assertEqual(per["v-2"], {"true": ["はい"], "false": ["いいえ"]})
        self.assertEqual(per["v-3"], {"true": ["380,000円"], "false": ["0円"]})
        self.assertTrue(all(a["key"] for a in q["affects"]))
        q2 = qs[1]
        self.assertEqual(q2["persons"], [])
        self.assertEqual(q2["affects"][0]["per_candidate"], {})

    def test_out_of_scope_boundaries_forms_filing(self) -> None:
        (g,) = self.d["out_of_scope"]
        self.assertEqual(g["category"], "対象外")
        self.assertEqual(g["record_ids"], ["f-8", "f-9"])
        self.assertEqual(g["count"], 1)
        self.assertEqual(g["values"][0]["value_id"], "v-5")
        (q,) = self.d["query_out_of_scope"]
        self.assertIn("まだ計算できない", q["display"])

        b1 = next(b for b in self.d["boundaries"] if b["id"] == "b-1")
        self.assertEqual(b1["criterion"], {"amount": 580_000, "basis": None})
        self.assertEqual(b1["criterion_basis"], {"law": "架空法第2条"})
        self.assertEqual(b1["difference"], 80_000)
        a1 = next(b for b in self.d["age_boundaries"] if b["id"] == "a-1")
        self.assertNotIn("secret_extra", a1)
        fa = next(f for f in self.d["forms"] if f["person"] == "p-a")
        self.assertEqual(fa["forms"][0]["fields"], 3)
        self.assertEqual(fa["forms"][0]["status_counts"], {"値あり": 2, "空欄": 1})
        self.assertEqual(self.d["filing"]["entries"], 3)
        self.assertEqual(len(self.d["filing"]["withheld"]), 2)
        self.assertNotIn("extra", self.d["filing"]["withheld"][0])


class DetailHelpersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.lr = R.LoadedResult(raw_result())

    def test_values_for_value_detail_forms_detail(self) -> None:
        ids = [v["id"] for v in R.values_for(self.lr, person="p-b", tkey="FY2027", institution="住民税")]
        self.assertEqual(ids, ["v-4"])
        ids = [v["id"] for v in R.values_for(self.lr, person="p-c", tkey=None, institution=None)]
        self.assertEqual(ids, ["v-2", "v-7"])
        self.assertIsNone(R.value_detail(self.lr, "v-nope"))
        vd = R.value_detail(self.lr, "v-2")
        assert vd is not None
        self.assertEqual([o["display"] for o in vd["outcomes_display"]], ["はい", "いいえ"])
        self.assertEqual([b["id"] for b in vd["boundaries"]], ["b-1"])
        fd = R.forms_detail(self.lr, "p-a", 2026)
        assert fd is not None
        self.assertEqual(fd["forms"][0]["fields"][0]["basis_entry"], {"law": "架空法第1条"})
        self.assertIsNone(R.forms_detail(self.lr, "p-a", 2025))


class AnswerTemplateTest(unittest.TestCase):
    def q(self, kind: str | None, target: dict) -> dict:
        return {"kind": kind, "target": {"kind": kind, **target}}

    def test_bool_candidate_and_period_when(self) -> None:
        q = self.q("判断.生計を一にするか", {"person": "p-c", "tax_year": 2026})
        t = R.answer_template(q, META, "true")
        assert t is not None
        self.assertEqual(t["section"], "judgments")
        self.assertEqual(t["record"]["value"], True)
        self.assertEqual(t["record"]["subject"], {"person": "p-c"})
        self.assertEqual(t["record"]["when"], {"from_on": "2026-01-01", "to_on": "2026-12-31"})
        t = R.answer_template(q, META, "false")
        assert t is not None
        self.assertIs(t["record"]["value"], False)
        t = R.answer_template(q, META, None)
        assert t is not None
        self.assertIsNone(t["record"]["value"])
        # 判定日しかない分かれ目でも、期間はその暦年の全体
        q = self.q("判断.生計を一にするか", {"person": "p-c", "on": "2027-06-30"})
        t = R.answer_template(q, META, "true")
        assert t is not None
        self.assertEqual(t["record"]["when"], {"from_on": "2027-01-01", "to_on": "2027-12-31"})

    def test_dependent_choice_value_shape_and_tax_year(self) -> None:
        q = self.q("選択.扶養の所属", {"dependent": "p-c", "tax_year": 2026})
        t = R.answer_template(q, META, "p-b")
        assert t is not None
        self.assertEqual(t["section"], "choices")
        self.assertEqual(t["record"]["when"], {"tax_year": 2026})
        self.assertEqual(t["record"]["subject"], {"dependent": "p-c"})
        self.assertEqual(t["record"]["value"], {"filer": "p-b", "document_type": "final_return", "section": "dependent_relative"})

    def test_fiscal_year_from_tax_year_and_mark(self) -> None:
        q = self.q("見込み.年間収入", {"person": "p-b", "tax_year": 2026})
        t = R.answer_template(q, META, "1300000")
        assert t is not None
        self.assertEqual(t["record"]["when"], {"fiscal_year": 2027})
        self.assertEqual(t["record"]["mark"], "予測")
        self.assertEqual(t["record"]["value"], "1300000")
        q = self.q("判断.住所の所在", {"person": "p-c", "on": "2026-12-31"})
        t = R.answer_template(q, META, "国内")
        assert t is not None
        self.assertEqual(t["record"]["when"], {"on": "2026-12-31"})

    def test_unknown_or_missing_kind(self) -> None:
        self.assertIsNone(R.answer_template({"target": {}}, META, "true"))
        self.assertIsNone(R.answer_template(self.q("判断.架空", {}), META, "true"))


if __name__ == "__main__":
    unittest.main()
