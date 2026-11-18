"""回答の依頼（招待リンク）：1回だけ・期限・取消し・メールの一致・端末でできることの制限。架空の世帯だけ。サーバーは起動しない。"""

from __future__ import annotations

import datetime as _dt
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from okura_web import db as dbm
from okura_web.auth import Auth
from okura_web.server import GUEST_COOKIE, Handler, HttpError, Router

HID = "hh-0000000000000000"


class InviteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # Windows は SQLite のファイルを掴んだまま
        self.db = dbm.Database(Path(self.tmp.name) / "t.sqlite3")
        self.auth = Auth(self.db, 24)
        with self.db.tx() as c:
            c.execute("INSERT INTO households(id, name, created_at) VALUES (?,?,?)", (HID, "架空家", dbm.now_iso()))
            c.execute("INSERT INTO persons VALUES (?,?,?,?,?)", (HID, "p-c", "架空一郎", "u-1", dbm.now_iso()))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def invite(self, email=None, days=7, qids=None):
        return self.auth.create_invite(HID, "p-c", "u-1", email=email, question_ids=qids, days=days)

    def test_secret_is_not_stored(self) -> None:
        iid, token = self.invite()
        row = self.db.one("SELECT * FROM invites WHERE id=?", (iid,))
        self.assertNotIn(token, str(dict(row)))

    def test_claim_once_and_guest_principal(self) -> None:
        iid, token = self.invite(qids=["q-1"])
        r = self.auth.claim_invite(token, None)
        self.assertIsInstance(r, tuple)
        device, csrf, inv = r
        self.assertEqual(inv["id"], iid)
        g = self.auth.guest(device)
        self.assertIsNotNone(g)
        assert g is not None
        self.assertEqual((g.kind, g.person_id, g.household_id, g.csrf), ("guest", "p-c", HID, csrf))
        self.assertTrue(g.is_human)
        self.assertEqual(g.extra["question_ids"], ["q-1"])
        self.assertEqual(g.actor, f"guest:{iid}")
        # 2回目は使えない
        again = self.auth.claim_invite(token, None)
        self.assertIsInstance(again, str)
        self.assertIn("もう使われた", again)

    def test_unknown_expired_revoked(self) -> None:
        self.assertIsInstance(self.auth.claim_invite("nope", None), str)
        self.assertIsInstance(self.auth.claim_invite("", None), str)
        iid, token = self.invite()
        with self.db.tx() as c:
            c.execute("UPDATE invites SET expires_at=? WHERE id=?", ((dbm.now() - _dt.timedelta(minutes=1)).isoformat(), iid))
        self.assertIn("期限", self.auth.claim_invite(token, None))
        iid2, token2 = self.invite()
        self.assertTrue(self.auth.revoke_invite(HID, iid2))
        self.assertIn("取り消", self.auth.claim_invite(token2, None))

    def test_revoke_after_claim_disables_device(self) -> None:
        iid, token = self.invite()
        device, _, _ = self.auth.claim_invite(token, None)  # type: ignore[misc]
        self.assertIsNotNone(self.auth.guest(device))
        self.auth.revoke_invite(HID, iid)
        self.assertIsNone(self.auth.guest(device))

    def test_email_must_match_verified_email(self) -> None:
        _, token = self.invite(email="kakuu-ichiro@example.invalid")
        self.assertIn("別のメール", self.auth.claim_invite(token, "someone-else@example.invalid"))
        r = self.auth.claim_invite(token, "kakuu-ichiro@example.invalid")
        self.assertIsInstance(r, tuple)
        row = self.db.one("SELECT claimed_email FROM invites")
        self.assertEqual(row["claimed_email"], "kakuu-ichiro@example.invalid")

    def test_days_are_clamped(self) -> None:
        iid, _ = self.invite(days=999)
        row = self.db.one("SELECT created_at, expires_at FROM invites WHERE id=?", (iid,))
        span = _dt.datetime.fromisoformat(row["expires_at"]) - _dt.datetime.fromisoformat(row["created_at"])
        self.assertLessEqual(span.days, Auth.INVITE_DAYS_MAX)


class GuestGateTest(unittest.TestCase):
    """招待リンクの端末は guest_ok の経路だけ使える。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # Windows は SQLite のファイルを掴んだまま
        self.db = dbm.Database(Path(self.tmp.name) / "t.sqlite3")
        self.auth = Auth(self.db, 24)
        with self.db.tx() as c:
            c.execute("INSERT INTO households(id, name, created_at) VALUES (?,?,?)", (HID, "架空家", dbm.now_iso()))
            c.execute("INSERT INTO persons VALUES (?,?,?,?,?)", (HID, "p-c", "架空一郎", "u-1", dbm.now_iso()))
        _, token = self.auth.create_invite(HID, "p-c", "u-1", email=None, question_ids=None, days=7)
        self.device, self.csrf, _ = self.auth.claim_invite(token, None)  # type: ignore[misc]
        self.router = Router()
        self.router.add("GET", "/api/guest/me", lambda req: {"who": req.principal.kind}, guest_ok=True)
        self.router.add("POST", "/api/guest/answer", lambda req: {"ok": True}, guest_ok=True)
        self.router.add("GET", "/api/records", lambda req: {"records": []})
        self.router.add("GET", "/api/status", lambda req: {"principal": req.principal is not None}, public=True)
        self.app = SimpleNamespace(auth=self.auth)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def call(self, method, path, csrf=None):
        headers = {"Cookie": f"{GUEST_COOKIE}={self.device}"}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        fake = SimpleNamespace(headers=headers, _origin_ok=lambda: True)
        return Handler._api(fake, self.app, self.router, method, path, {})  # type: ignore[arg-type]

    def test_guest_routes_work(self) -> None:
        self.assertIn(b"guest", self.call("GET", "/api/guest/me").body)
        self.assertEqual(self.call("POST", "/api/guest/answer", csrf=self.csrf).status, 200)

    def test_guest_needs_csrf_for_writes(self) -> None:
        with self.assertRaises(HttpError) as cm:
            self.call("POST", "/api/guest/answer")
        self.assertEqual(cm.exception.code, "csrf")

    def test_guest_cannot_use_other_routes(self) -> None:
        with self.assertRaises(HttpError) as cm:
            self.call("GET", "/api/records")
        self.assertEqual(cm.exception.code, "guest_only")

    def test_public_routes_do_not_see_guest(self) -> None:
        self.assertIn(b"false", self.call("GET", "/api/status").body)


class GuestAnswerTest(unittest.TestCase):
    """端末から答える：その人あての「選ぶ」質問だけ・候補の検査・判断台帳への書き込み（書き込みは捕まえる）。"""

    def setUp(self) -> None:
        from okura_web import api, api_invite
        from okura_web.auth import Principal
        from tests import _fixtures as fx

        self.api, self.mod = api, api_invite
        q_mine = {"id": "s-seikei-p-c", "means": "判断", "kind": "判断.生計を一にするか", "candidates": ["true", "false"],
                  "target": {"kind": "判断.生計を一にするか", "person": "p-c", "tax_year": 2026}, "persons": ["p-c"], "years": [2026],
                  "affects": [{"person": "p-a", "per_candidate": {"true": ["3,000,000円"]}}]}
        q_other = dict(q_mine, id="s-other", persons=["p-b"], target={"kind": "判断.生計を一にするか", "person": "p-b", "tax_year": 2026})
        q_fact = dict(q_mine, id="s-fact", means="事実", candidates=[])
        digest = {"questions": [q_mine, q_other, q_fact]}
        self.saved = []
        self._old_app = getattr(api, "APP", None)
        api.APP = SimpleNamespace(  # type: ignore[assignment]
            latest_result=lambda hid: {"result_hash": "r1"},
            load_digest=lambda hid, h: digest,
            meta=lambda: fx.META,
        )
        self._old_write = api_invite.write_judgment
        api_invite.write_judgment = lambda req, section, rec, basis: self.saved.append((section, rec, basis)) or {"ok": True, "record_id": "j-1"}  # type: ignore[assignment]
        self._old_audit = api_invite._audit
        api_invite._audit = lambda *a, **k: None  # type: ignore[assignment]
        self.principal = Principal("guest", "guest:inv-1", "架空一郎", household_id=HID, role="guest", person_id="p-c",
                                   csrf="c", extra={"invite_id": "inv-1", "question_ids": []})

    def tearDown(self) -> None:
        self.api.APP = self._old_app  # type: ignore[assignment]
        self.mod.write_judgment = self._old_write  # type: ignore[assignment]
        self.mod._audit = self._old_audit  # type: ignore[assignment]

    def req(self, body):
        import json as _json
        from okura_web.server import Request
        raw = _json.dumps(body).encode()
        handler = SimpleNamespace(headers={"Content-Length": str(len(raw))}, rfile=SimpleNamespace(read=lambda n: raw),
                                  server=SimpleNamespace(app=SimpleNamespace(cfg=SimpleNamespace(max_json_bytes=1_000_000))))
        return Request(handler, "POST", "/api/guest/answer", {}, {}, self.principal, None)  # type: ignore[arg-type]

    def test_only_own_choice_questions_without_amounts(self) -> None:
        qs = self.mod._guest_questions(HID, "p-c", [])
        self.assertEqual([q["id"] for q in qs], ["s-seikei-p-c"])
        self.assertNotIn("affects", qs[0])  # ほかの人の金額は見せない

    def test_answer_writes_judgment_by_the_person(self) -> None:
        self.mod.guest_answer(self.req({"question_id": "s-seikei-p-c", "candidate": "false", "note": "別に暮らしている"}))
        section, rec, basis = self.saved[0]
        self.assertEqual(section, "judgments")
        self.assertEqual(rec["value"], False)
        self.assertEqual(rec["subject"], {"person": "p-c"})
        self.assertIn("inv-1", basis)
        self.assertIn("別に暮らしている", basis)

    def test_rejects_other_persons_question_and_bad_candidate(self) -> None:
        with self.assertRaises(HttpError):
            self.mod.guest_answer(self.req({"question_id": "s-other", "candidate": "true"}))
        with self.assertRaises(HttpError):
            self.mod.guest_answer(self.req({"question_id": "s-seikei-p-c", "candidate": "maybe"}))
        self.assertEqual(self.saved, [])

    def test_limited_to_invited_questions(self) -> None:
        self.principal.extra["question_ids"] = ["s-something-else"]
        with self.assertRaises(HttpError):
            self.mod.guest_answer(self.req({"question_id": "s-seikei-p-c", "candidate": "true"}))


if __name__ == "__main__":
    unittest.main()
