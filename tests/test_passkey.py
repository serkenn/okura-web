"""パスキー（api_passkey）：公開のホスト名だけ・challenge は1回だけ・userHandle の照合・登録はログインの人だけ。

webauthn のサブプロセスは呼ばない（_bridge を差し替える）。架空のアカウントだけ。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from okura_web import api, api_passkey
from okura_web import db as dbm
from okura_web.auth import Auth, Principal
from okura_web.server import HttpError, Request

HOST = "kakuu.example.invalid"


class PasskeyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = dbm.Database(Path(self.tmp.name) / "t.sqlite3")
        self.auth = Auth(self.db, 24)
        with self.db.tx() as c:
            c.execute("INSERT INTO users(id, login, display_name, pw_hash, created_at) VALUES ('u-1','kakuu','架空太郎','x',?)", (dbm.now_iso(),))
        self.calls: list[dict] = []
        self.verify_ok = True

        def bridge(payload):
            self.calls.append(payload)
            op = payload["op"]
            if op.endswith("options"):
                return {"ok": True, "options": {"challenge": payload["challenge"]}}
            if op == "register_verify":
                return {"ok": self.verify_ok, "credential_id": "cred-1", "public_key": "pk", "sign_count": 0}
            return {"ok": self.verify_ok, "sign_count": 5}

        self._old = (getattr(api, "APP", None), api_passkey._bridge, api_passkey._audit)
        api.APP = SimpleNamespace(db=self.db, auth=self.auth, cfg=SimpleNamespace(session_hours=1, max_json_bytes=1_000_000))  # type: ignore[assignment]
        api_passkey._bridge = bridge  # type: ignore[assignment]
        api_passkey._audit = lambda *a, **k: None  # type: ignore[assignment]
        api_passkey._RATE.clear()
        self.user = Principal("session", "u-1", "架空太郎", household_id="hh-0", role="admin", person_id="p-a", csrf="c")

    def tearDown(self) -> None:
        api.APP, api_passkey._bridge, api_passkey._audit = self._old  # type: ignore[assignment]
        self.tmp.cleanup()

    def req(self, body=None, *, host=HOST, principal=None):
        raw = json.dumps(body or {}).encode()
        handler = SimpleNamespace(
            headers={"Content-Length": str(len(raw)), "Host": host}, rfile=SimpleNamespace(read=lambda n: raw), client_address=("127.0.0.1", 1),
            server=SimpleNamespace(public_hosts={HOST}, app=api.APP),
        )
        return Request(handler, "POST", "/x", {}, {}, principal, None)  # type: ignore[arg-type]

    def register(self):
        o = api_passkey.register_options(self.req(principal=self.user))
        api_passkey.register_verify(self.req({"challenge_id": o["challenge_id"], "credential": {"id": "cred-1"}}, principal=self.user))
        return self.db.one("SELECT * FROM passkeys")

    def test_only_public_host(self) -> None:
        with self.assertRaises(HttpError) as cm:
            api_passkey.login_options(self.req(host="127.0.0.1:8765"))
        self.assertEqual(cm.exception.code, "passkey_host")

    def test_register_uses_server_rp_and_requires_session(self) -> None:
        row = self.register()
        self.assertEqual(row["user_id"], "u-1")
        verify = next(c for c in self.calls if c["op"] == "register_verify")
        self.assertEqual((verify["rp_id"], verify["origin"]), (HOST, f"https://{HOST}"))
        guest = Principal("guest", "guest:inv-1", "x", household_id="hh-0", person_id="p-c", csrf="c")
        with self.assertRaises(HttpError):
            api_passkey.register_options(self.req(principal=guest))

    def test_challenge_is_single_use(self) -> None:
        self.register()
        o = api_passkey.login_options(self.req())
        cred = {"id": "cred-1", "rawId": "cred-1", "response": {"userHandle": self.db.one("SELECT user_handle FROM passkeys")["user_handle"]}}
        resp = api_passkey.login_verify(self.req({"challenge_id": o["challenge_id"], "credential": cred}))
        self.assertIn("okura_session=", resp.headers["Set-Cookie"])
        self.assertEqual(self.db.one("SELECT sign_count FROM passkeys")["sign_count"], 5)
        with self.assertRaises(HttpError) as cm:
            api_passkey.login_verify(self.req({"challenge_id": o["challenge_id"], "credential": cred}))
        self.assertEqual(cm.exception.code, "passkey_challenge")

    def test_user_handle_must_match_and_failed_verify_rejected(self) -> None:
        self.register()
        o = api_passkey.login_options(self.req())
        with self.assertRaises(HttpError) as cm:
            api_passkey.login_verify(self.req({"challenge_id": o["challenge_id"], "credential": {"rawId": "cred-1", "response": {"userHandle": "someone-else"}}}))
        self.assertEqual(cm.exception.code, "passkey_unknown")
        handle = self.db.one("SELECT user_handle FROM passkeys")["user_handle"]
        self.verify_ok = False
        o = api_passkey.login_options(self.req())
        with self.assertRaises(HttpError) as cm:
            api_passkey.login_verify(self.req({"challenge_id": o["challenge_id"], "credential": {"rawId": "cred-1", "response": {"userHandle": handle}}}))
        self.assertEqual(cm.exception.code, "passkey_invalid")

    def test_revoked_passkey_cannot_login(self) -> None:
        self.register()
        with self.db.tx() as c:
            c.execute("UPDATE passkeys SET revoked_at=?", (dbm.now_iso(),))
        o = api_passkey.login_options(self.req())
        with self.assertRaises(HttpError):
            api_passkey.login_verify(self.req({"challenge_id": o["challenge_id"], "credential": {"rawId": "cred-1", "response": {"userHandle": "x"}}}))


if __name__ == "__main__":
    unittest.main()
