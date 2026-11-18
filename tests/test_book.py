"""家計簿の台帳（book.py）：取引の形・追記と鎖・作り直した beancount・残高の確認。架空の取引だけ。

記録層のサブプロセスは呼ばない（engine.transactions_file を差し替える）。本物の検査は手で通す（.work/scratch/smoke_book.py）。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from okura_web.book import Book, BookError, balance_checks, check_txn, clean_text, fold, new_tx_id, render
from okura_web.engine import EngineError


class FakeEngine:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False

    def transactions_file(self, ledger: Path, root: Path) -> dict:
        self.calls += 1
        if self.fail:
            raise EngineError("x", code="ledger_problems", problems=[{"code": "beancount_error"}])
        assert ledger.read_text(encoding="utf-8").startswith(";")
        return {}


def tx(tid: str, amount: int = -3000, cat: str = "Expenses:Food", **kw) -> dict:
    return {"id": new_tx_id(tid), "date": kw.pop("date", "2026-11-01"), "payee": "架空スーパー", "narration": "",
            "postings": [{"account": "Liabilities:Card:K", "amount": amount}, {"account": cat, "amount": -amount}], **kw}


class CheckTxnTest(unittest.TestCase):
    def test_balanced_and_shapes(self) -> None:
        self.assertEqual(check_txn(tx("a"))["postings"][0]["amount"], -3000)
        bad = [
            {**tx("a"), "postings": [{"account": "Liabilities:Card:K", "amount": -3000}, {"account": "Expenses:Food", "amount": 2999}]},
            {**tx("a"), "date": "2026-02-30"},
            {**tx("a"), "id": "x"},
            {**tx("a"), "postings": [{"account": "expenses:food", "amount": 1}, {"account": "Expenses:Food", "amount": -1}]},
            {**tx("a"), "postings": [{"account": "Expenses:Food", "amount": 1.5}, {"account": "Expenses:Food", "amount": -1.5}]},
            {**tx("a"), "postings": [{"account": "Expenses:Food", "amount": True}, {"account": "Expenses:Food", "amount": -1}]},
            {**tx("a"), "source": "src"},  # 取得元の ID がない
        ]
        for t in bad:
            with self.subTest(t=str(t)[:60]):
                with self.assertRaises(BookError):
                    check_txn(t)

    def test_clean_text_drops_controls_and_bidi(self) -> None:
        self.assertEqual(clean_text("架空‮店\n名\x00"), "架空 店 名")

    def test_render_escapes_quotes(self) -> None:
        st = fold([])
        st.accounts.update({"Liabilities:Card:K": "2000-01-01", "Expenses:Food": "2000-01-01"})
        st.txns[new_tx_id("a")] = check_txn({**tx("a"), "payee": 'A "B" \\ C'})
        text = render(st)
        self.assertIn('"A \\"B\\" \\\\ C"', text)
        self.assertIn("2000-01-01 open Expenses:Food JPY", text)


class BookAppendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.eng = FakeEngine()
        self.book = Book(Path(self.tmp.name), "hh-kakuu", self.eng)  # type: ignore[arg-type]
        self.book.append([{"op": "open", "account": "Liabilities:Card:K"}, {"op": "open", "account": "Expenses:Food"},
                          {"op": "open", "account": "Expenses:Medical"}], by="u-1")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_correct_delete_are_appended(self) -> None:
        t = tx("a", source="src", source_id="s-1")
        self.book.append([{"op": "add", "txn": t}], by="u-1")
        self.book.append([{"op": "correct", "txn": {**t, "postings": [{"account": "Liabilities:Card:K", "amount": -3000},
                                                                      {"account": "Expenses:Medical", "amount": 3000}]}}], by="u-1")
        st = self.book.append([{"op": "delete", "id": t["id"], "reason": "二重"}], by="u-1")
        self.assertNotIn(t["id"], st.txns)
        self.assertNotIn(("src", "s-1"), st.sources)  # 取り消した取引の取得元の ID は外す（登録し直せる。二重の取り込みは book_imports で防ぐ）
        lines = (Path(self.tmp.name) / "book" / "book.jsonl").read_bytes().splitlines()
        self.assertEqual(len(lines), 6)  # 何も消えていない（追記のみ）
        with self.assertRaises(BookError):
            self.book.append([{"op": "add", "txn": t}], by="u-1")  # 同じ ID は足せない

    def test_unknown_account_and_reason_required(self) -> None:
        with self.assertRaises(BookError):
            self.book.append([{"op": "add", "txn": tx("b", cat="Expenses:Nope")}], by="u-1")
        self.book.append([{"op": "add", "txn": tx("b")}], by="u-1")
        with self.assertRaises(BookError):
            self.book.append([{"op": "delete", "id": new_tx_id("b"), "reason": ""}], by="u-1")

    def test_validation_failure_changes_nothing(self) -> None:
        before = (Path(self.tmp.name) / "book" / "book.jsonl").read_bytes()
        self.eng.fail = True
        with self.assertRaises(BookError):
            self.book.append([{"op": "add", "txn": tx("c")}], by="u-1")
        self.assertEqual((Path(self.tmp.name) / "book" / "book.jsonl").read_bytes(), before)

    def test_tampering_breaks_the_chain(self) -> None:
        self.book.append([{"op": "add", "txn": tx("d")}], by="u-1")
        self.book.append([{"op": "add", "txn": tx("d2")}], by="u-1")
        log = Path(self.tmp.name) / "book" / "book.jsonl"
        lines = log.read_bytes().split(b"\n")
        lines[3] = lines[3].replace(b"-3000", b"-30", 1)  # 途中の行（最後の行の書き換えは鎖では見つけられない。モジュールの説明を参照）
        log.write_bytes(b"\n".join(lines))
        self.book._cache = None
        with self.assertRaises(BookError) as cm:
            self.book.state()
        self.assertEqual(cm.exception.code, "book_chain")

    def test_balance_checks_and_only_matching_written(self) -> None:
        self.book.append([{"op": "add", "txn": tx("e", -1000, date="2026-11-01")}, {"op": "add", "txn": tx("f", -500, date="2026-11-03")}], by="u-1")
        st = self.book.append([
            {"op": "balance", "account": "Liabilities:Card:K", "date": "2026-11-01", "amount": -1000},
            {"op": "balance", "account": "Liabilities:Card:K", "date": "2026-11-03", "amount": -9999},
        ], by="u-1")
        checks = {c["date"]: c for c in balance_checks(st)}
        self.assertTrue(checks["2026-11-01"]["ok"])
        self.assertFalse(checks["2026-11-03"]["ok"])
        self.assertEqual(checks["2026-11-03"]["calculated"], -1500)
        text = render(st)
        self.assertIn("2026-11-02 balance Liabilities:Card:K  -1000 JPY", text)
        self.assertNotIn("-9999", text)


if __name__ == "__main__":
    unittest.main()
