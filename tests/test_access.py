"""見える範囲（Access）と、外部に渡すときの伏せ字（redact_record）・人の ID の取り出し（persons_in）。"""

from __future__ import annotations

import copy
import json
import unittest

from okura_web.access import HIDDEN_PERSON, MASK, persons_in, redact_record, replace_ids

from ._fixtures import consent, make_access


class IsMineTest(unittest.TestCase):
    def test_self_and_managed_without_account(self) -> None:
        acc = make_access("p-a", managed={"p-c"}, account_persons={"p-a", "p-b"})
        for pid in ("p-a", "p-c"):
            self.assertTrue(acc.is_mine(pid))
            self.assertTrue(acc.can_decide_for(pid))

    def test_managed_person_with_account_is_not_mine(self) -> None:
        # p-b は自分のアカウントを持つ：管理する人の登録が残っていても、決めるのは本人
        acc = make_access("p-a", managed={"p-b", "p-c"}, account_persons={"p-a", "p-b"})
        self.assertFalse(acc.is_mine("p-b"))
        self.assertFalse(acc.can_decide_for("p-b"))

    def test_unmanaged_person_without_account_is_not_mine(self) -> None:
        acc = make_access("p-b", managed=set(), account_persons={"p-a", "p-b"})
        self.assertFalse(acc.is_mine("p-c"))
        self.assertFalse(acc.can_decide_for("p-c"))


class SeesNumbersTest(unittest.TestCase):
    def test_mine_visible_others_hidden_by_default(self) -> None:
        acc = make_access("p-a")
        self.assertTrue(acc.sees_numbers("p-a"))
        self.assertTrue(acc.sees_numbers("p-c"))  # 管理しているアカウントのない子
        self.assertFalse(acc.sees_numbers("p-b"))

    def test_consent_and_revocation(self) -> None:
        self.assertTrue(make_access("p-a", consents={("p-b", "share_numbers"): consent(1)}).sees_numbers("p-b"))
        self.assertFalse(make_access("p-a", consents={("p-b", "share_numbers"): consent(0)}).sees_numbers("p-b"))

    def test_other_kinds_do_not_imply_numbers(self) -> None:
        acc = make_access("p-a", consents={("p-b", k): consent(1) for k in ("share_details", "share_originals", "external_ai")})
        self.assertFalse(acc.sees_numbers("p-b"))


class SeesDetailsTest(unittest.TestCase):
    def test_recorded_by_me_is_visible_even_without_consent(self) -> None:
        acc = make_access("p-a")
        self.assertTrue(acc.sees_details_of({"p-b"}, recorded_by="p-a"))
        self.assertTrue(acc.sees_details_of(set(), recorded_by="p-a"))
        self.assertFalse(acc.sees_details_of({"p-b"}, recorded_by="p-b"))

    def test_involving_mine_is_visible(self) -> None:
        acc = make_access("p-a")
        self.assertTrue(acc.sees_details_of({"p-b", "p-c"}))

    def test_all_involved_must_consent(self) -> None:
        acc = make_access("p-c", account_persons={"p-a", "p-b", "p-c"}, managed=set(),
                          consents={("p-a", "share_details"): consent(1)})
        self.assertFalse(acc.sees_details_of({"p-a", "p-b"}))
        acc.consents[("p-b", "share_details")] = consent(1)
        self.assertTrue(acc.sees_details_of({"p-a", "p-b"}))

    def test_numbers_consent_does_not_grant_details(self) -> None:
        acc = make_access("p-a", consents={("p-b", "share_numbers"): consent(1)})
        self.assertFalse(acc.sees_details_of({"p-b"}))

    def test_no_persons_or_no_principal_person(self) -> None:
        acc = make_access("p-a")
        self.assertFalse(acc.sees_details_of(set()))
        self.assertFalse(acc.sees_details_of([None, ""]))  # type: ignore[list-item]
        acc = make_access(None, managed=set())  # 人に結び付いていない主体：記録者が空でも一致しない
        self.assertFalse(acc.sees_details_of({"p-b"}, recorded_by=None))
        self.assertFalse(acc.sees_details_of({"p-b"}, recorded_by=""))


class SeesOriginalTest(unittest.TestCase):
    def test_uploader_or_owner_mine(self) -> None:
        acc = make_access("p-a", user_id="u-1")
        self.assertTrue(acc.sees_original("p-b", "u-1"))
        self.assertTrue(acc.sees_original("p-c", "u-2"))

    def test_other_needs_share_originals(self) -> None:
        acc = make_access("p-a", user_id="u-1", consents={("p-b", "share_details"): consent(1)})
        self.assertFalse(acc.sees_original("p-b", "u-2"))
        acc.consents[("p-b", "share_originals")] = consent(1)
        self.assertTrue(acc.sees_original("p-b", "u-2"))


class ExternalAndPseudonymTest(unittest.TestCase):
    def test_external_ok_needs_explicit_consent(self) -> None:
        acc = make_access("p-a", consents={("p-b", "external_ai"): consent(1)})
        self.assertFalse(acc.external_ok("p-a"))  # 自分でも同意がなければ外部に出さない
        self.assertTrue(acc.external_ok("p-b"))

    def test_pseudonyms_and_replace_ids(self) -> None:
        acc = make_access("p-a", all_persons=["p-b", "p-a", "p-c"])
        self.assertEqual(acc.pseudonyms(), {"p-b": "人物1", "p-a": "人物2", "p-c": "人物3"})
        obj = {"person": "p-b", "list": ["p-b", "p-a", 3], "nested": {"x": "p-b"}, "p-b": "key-not-replaced"}
        out = replace_ids(obj, {"p-b": HIDDEN_PERSON})
        self.assertEqual(out, {"person": HIDDEN_PERSON, "list": [HIDDEN_PERSON, "p-a", 3], "nested": {"x": HIDDEN_PERSON}, "p-b": "key-not-replaced"})


class PersonsInTest(unittest.TestCase):
    KNOWN = {"p-a", "p-b", "p-c"}

    def test_roles_subject_value_and_judges(self) -> None:
        rec = {
            "id": "j-1",
            "kind": "選択.扶養の所属",
            "chosen_by": "p-a",
            "subject": {"dependent": "p-c"},
            "value": {"filer": "p-b"},
            "roles": {"payer": "p-x-unknown"},
        }
        self.assertEqual(persons_in(rec, self.KNOWN), {"p-a", "p-b", "p-c"})
        rec = {"id": "j-2", "judged_by": {"person": "p-b"}, "subject": {"person": "p-c"}}
        self.assertEqual(persons_in(rec, self.KNOWN), {"p-b", "p-c"})

    def test_attributes_and_note_not_scanned(self) -> None:
        rec = {"id": "f-1", "roles": {"recipient": "p-a"}, "attributes": {"counterparty": "p-b"}, "note": "p-c"}
        self.assertEqual(persons_in(rec, self.KNOWN), {"p-a"})

    def test_person_record_itself(self) -> None:
        self.assertEqual(persons_in({"id": "p-c", "birth_on": "2010-05-05"}, self.KNOWN), {"p-c"})
        self.assertEqual(persons_in({"id": "p-z", "birth_on": "2010-05-05"}, self.KNOWN), set())
        self.assertEqual(persons_in(["p-a"], self.KNOWN), set())  # 記録でないもの


class RedactRecordTest(unittest.TestCase):
    def test_fact_record(self) -> None:
        sha = "ab" * 32
        rec = {
            "id": "f-1",
            "kind": "salary_payment",
            "roles": {"recipient": "p-a"},
            "when": {"on": "2026-01-25"},
            "amounts": {"gross": 300_000, "withholding_tax": 5_000},
            "attributes": {
                "counterparty": "Kakuu Shoji",  # ASCII でも名前の欄は伏せる
                "municipality": "Kakuu-shi",
                "branch": "架空支店",  # 欄の名前が無害でも ASCII でない文字列は伏せる
                "slip_type": "salary",
                "medical_kinds": ["medical_treatment"],
                "visits": [{"provider_name": "Kakuu Clinic", "count": 2}],
            },
            "source": {"evidence_sha256": [sha], "transaction_ids": ["tx-1"]},
            "note": "plain ascii note",
            "mark": "予測",
        }
        before = copy.deepcopy(rec)
        out = redact_record(rec)
        self.assertEqual(rec, before, "入力を書き換えない")
        for k in ("id", "kind", "roles", "when", "amounts", "mark"):
            self.assertEqual(out[k], rec[k])
        a = out["attributes"]
        self.assertEqual(a["counterparty"], MASK)
        self.assertEqual(a["municipality"], MASK)
        self.assertEqual(a["branch"], MASK)
        self.assertEqual(a["slip_type"], "salary")
        self.assertEqual(a["medical_kinds"], ["medical_treatment"])
        self.assertEqual(a["visits"], [{"provider_name": MASK, "count": 2}])
        self.assertEqual(out["source"], {"evidence": "あり"})
        self.assertNotIn(sha, json.dumps(out))
        self.assertNotIn("tx-1", json.dumps(out))
        self.assertEqual(out["note"], MASK)

    def test_person_record_birth_to_year(self) -> None:
        out = redact_record({"id": "p-c", "birth_on": "2010-05-05", "death_on": "2090-01-02", "display_name": "架空一郎"})
        self.assertEqual(out["birth_on"], "2010")
        self.assertEqual(out["death_on"], "2090")
        self.assertEqual(out["display_name"], MASK)

    def test_judgment_record(self) -> None:
        rec = {
            "id": "j-1",
            "kind": "判断.生計を一にするか",
            "judged_by": {"person": "p-a"},
            "judged_at": "2026-03-01T09:00:00+09:00",
            "subject": {"person": "p-c", "label": "Kakuu"},
            "value": "同居している",
            "basis": {"memo": "Kakuu memo", "ref": "law-1"},
        }
        out = redact_record(rec)
        self.assertEqual(out["judged_by"], {"person": "p-a"})
        self.assertEqual(out["subject"], {"person": "p-c", "label": MASK})
        self.assertEqual(out["value"], MASK)
        self.assertEqual(out["basis"], {"memo": MASK, "ref": "law-1"})
        self.assertEqual(out["judged_at"], rec["judged_at"])
        # 家族の外の判断者（名前のラベル）は伏せる
        out = redact_record({"id": "j-2", "judged_by": {"label": "架空の税理士"}})
        self.assertEqual(out["judged_by"], MASK)
        out = redact_record({"id": "j-3", "judged_by": "Kakuu Taro"})
        self.assertEqual(out["judged_by"], MASK)

    def test_ascii_value_and_empty_source_kept(self) -> None:
        out = redact_record({"id": "c-1", "chosen_by": "p-a", "value": {"filer": "p-a"}, "source": None})
        self.assertEqual(out["value"], {"filer": "p-a"})
        self.assertEqual(out["chosen_by"], "p-a")
        self.assertIsNone(out["source"])


if __name__ == "__main__":
    unittest.main()
