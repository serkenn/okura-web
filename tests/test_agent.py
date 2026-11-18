"""写真の読み取りの結果 → 記録の下書き（agent.to_record と、その部品）。LLM は呼ばない。"""

from __future__ import annotations

import unittest

from okura_web.agent import _date, _first_json, _int, to_record


class IntTest(unittest.TestCase):
    def test_accepts_and_rejects(self) -> None:
        self.assertEqual(_int(1200), 1200)
        self.assertEqual(_int(0), 0)
        self.assertEqual(_int("1,200円"), 1200)
        self.assertEqual(_int("¥ 3,000"), 3000)
        self.assertEqual(_int("12，345"), 12345)
        for v in (True, False, -1, 10**12 + 1, 1.5, "abc", "-500", "1.5", "", None, [1]):
            with self.subTest(v=v):
                self.assertIsNone(_int(v))

    def test_unicode_digit_like_string_does_not_raise(self) -> None:
        # 直した不具合：str.isdigit() は "²"・"①" も True（int() が ValueError を投げていた）
        self.assertIsNone(_int("²"))

    def test_string_upper_bound_matches_int_path(self) -> None:
        # 直した不具合：整数では 10**12 を超えると None、文字列では上限を確かめていなかった
        self.assertIsNone(_int(str(10**12 + 1)))


class DateAndJsonTest(unittest.TestCase):
    def test_date(self) -> None:
        self.assertEqual(_date("2026-01-25"), "2026-01-25")
        for v in ("2026/01/25", "2026-1-25", "2026-01-25T00:00", "2026-02-30", 20260125, None):
            with self.subTest(v=v):
                self.assertIsNone(_date(v))

    def test_first_json(self) -> None:
        text = '読み取った結果：\n```json\n{"doc_type": "donation_receipt", "amount": 10000}\n```'
        self.assertEqual(_first_json(text), {"doc_type": "donation_receipt", "amount": 10000})
        self.assertIsNone(_first_json("JSON はない"))
        self.assertIsNone(_first_json("{not json}"))
        self.assertIsNone(_first_json('{"a": 1} と {"b": 2}'))  # 貪欲な一致で2つ目まで取って読めない


class ToRecordTest(unittest.TestCase):
    def test_salary_payslip(self) -> None:
        read = {
            "doc_type": "salary_payslip",
            "date": "2026-01-25",
            "counterparty": "架空商事",
            "gross": "300,000円",
            "withholding_tax": 5000,
            "social_insurance": 42000,
            "commuting_allowance": None,
        }
        section, rec = to_record(read, "p-a")  # type: ignore[misc]
        self.assertEqual(section, "facts")
        self.assertEqual(rec["kind"], "salary_payment")
        self.assertEqual(rec["roles"], {"recipient": "p-a"})
        self.assertEqual(rec["when"], {"on": "2026-01-25"})
        self.assertEqual(rec["amounts"], {"gross": 300000, "withholding_tax": 5000, "social_insurance_withheld": 42000})
        self.assertEqual(rec["attributes"], {"counterparty": "架空商事", "due_on": "2026-01-25"})

    def test_withholding_slip(self) -> None:
        _, rec = to_record({"doc_type": "withholding_slip", "tax_year": 2025, "payment_amount": 3_600_000}, "p-b")  # type: ignore[misc]
        self.assertEqual(rec["kind"], "withholding_slip")
        self.assertEqual(rec["when"], {"tax_year": 2025})
        self.assertEqual(rec["amounts"], {"payment_amount": 3_600_000})
        self.assertEqual(rec["attributes"], {"slip_type": "salary"})
        # 年分がなければ日付の年。支払金額がなければ総支給額
        _, rec = to_record({"doc_type": "withholding_slip", "date": "2026-01-31", "gross": 1000}, "p-b")  # type: ignore[misc]
        self.assertEqual(rec["when"], {"tax_year": 2026})
        self.assertEqual(rec["amounts"], {"payment_amount": 1000})

    def test_medical_receipt(self) -> None:
        _, rec = to_record({"doc_type": "medical_receipt", "date": "2026-03-01", "counterparty": "架空医院", "amount": "4,560"}, "p-c")  # type: ignore[misc]
        self.assertEqual(rec["kind"], "medical_payment")
        self.assertEqual(rec["roles"], {"payer": "p-c", "patient": "p-c"})
        self.assertEqual(rec["amounts"], {"amount": 4560})
        self.assertEqual(rec["attributes"], {"medical_kinds": ["medical_treatment"], "incurred_on": "2026-03-01", "provider": "架空医院"})

    def test_expense_donation_and_rejections(self) -> None:
        _, rec = to_record({"doc_type": "expense_receipt", "amount": 800, "counterparty": "架空文具店"}, "p-a")  # type: ignore[misc]
        self.assertEqual((rec["kind"], rec["roles"], rec["when"]), ("business_expense", {"payer": "p-a"}, {}))
        self.assertEqual(rec["attributes"], {"expense_category": "other", "counterparty": "架空文具店"})
        _, rec = to_record({"doc_type": "donation_receipt", "amount": "abc", "counterparty": "架空村"}, "p-a")  # type: ignore[misc]
        self.assertEqual(rec["kind"], "donation")
        self.assertEqual(rec["roles"], {"donor": "p-a"})
        self.assertEqual(rec["amounts"], {})
        self.assertEqual(rec["attributes"], {"recipient_name": "架空村"})
        # 制御文字・長すぎる取引先は捨てる。種類が分からなければ下書きを作らない
        _, rec = to_record({"doc_type": "expense_receipt", "amount": 1, "counterparty": "架空\x00店"}, "p-a")  # type: ignore[misc]
        self.assertNotIn("counterparty", rec["attributes"])
        _, rec = to_record({"doc_type": "expense_receipt", "amount": 1, "counterparty": "x" * 101}, "p-a")  # type: ignore[misc]
        self.assertNotIn("counterparty", rec["attributes"])
        self.assertIsNone(to_record({"doc_type": "other"}, "p-a"))
        self.assertIsNone(to_record({}, "p-a"))


if __name__ == "__main__":
    unittest.main()
