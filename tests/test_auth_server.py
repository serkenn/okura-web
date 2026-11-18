"""パスワードのハッシュ・強さの確かめ、Principal、Router.match（405 を含む）。サーバーは起動しない。"""

from __future__ import annotations

import base64
import unittest

from okura_web.auth import Principal, check_password_strength, hash_password, verify_password
from okura_web.server import HttpError, Router


class PasswordTest(unittest.TestCase):
    PW = "kakuu-password-2026"

    def test_round_trip(self) -> None:
        h = hash_password(self.PW)
        self.assertTrue(h.startswith("scrypt$16384$8$1$"))
        self.assertNotIn(self.PW, h)
        self.assertTrue(verify_password(self.PW, h))
        self.assertFalse(verify_password(self.PW + "x", h))
        self.assertFalse(verify_password("", h))
        self.assertNotEqual(h, hash_password(self.PW))  # 塩が毎回違う
        pw = "架空のパスワードです"
        self.assertTrue(verify_password(pw, hash_password(pw)))

    def test_malformed_or_tampered_stored_hash(self) -> None:
        h = hash_password(self.PW)
        algo, n, r, p, salt, dk = h.split("$")
        flipped = base64.b64encode(bytes([base64.b64decode(dk)[0] ^ 1]) + base64.b64decode(dk)[1:]).decode()
        for stored in (
            "",
            "plain-text",
            "bcrypt$" + "$".join([n, r, p, salt, dk]),
            "$".join([algo, n, r, p, salt, flipped]),
            "$".join([algo, "x", r, p, salt, dk]),
            "$".join([algo, n, r, p, "!!notbase64!!", dk]),
            h + "$extra",
        ):
            with self.subTest(stored=stored[:20]):
                self.assertFalse(verify_password(self.PW, stored))

    def test_strength(self) -> None:
        self.assertIsNotNone(check_password_strength(""))
        self.assertIsNotNone(check_password_strength("123456789"))
        self.assertIsNone(check_password_strength("1234567890"))


class PrincipalTest(unittest.TestCase):
    def test_session_and_token_actor(self) -> None:
        s = Principal("session", "u-1", "架空太郎")
        self.assertTrue(s.is_human)
        self.assertEqual(s.actor, "user:u-1")
        t = Principal("token", "u-1", "架空太郎", token_id="tok-1", scopes=("read",))
        self.assertFalse(t.is_human)
        self.assertEqual(t.actor, "token:tok-1")


def _h1(req):  # noqa: ANN001, ANN202
    return "h1"


def _h2(req):  # noqa: ANN001, ANN202
    return "h2"


class RouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.r = Router()
        self.r.add("GET", "/api/records/{rid}", _h1, token_ok=True)
        self.r.add("POST", "/api/records/{rid}/correct", _h2)
        self.r.add("DELETE", "/api/records/{rid}", _h2)

    def test_match_with_params_and_opts(self) -> None:
        found = self.r.match("GET", "/api/records/f-1")
        assert found is not None
        fn, params, opts = found
        self.assertIs(fn, _h1)
        self.assertEqual(params, {"rid": "f-1"})
        self.assertEqual(opts, {"token_ok": True})
        found = self.r.match("DELETE", "/api/records/f-1")
        assert found is not None
        self.assertIs(found[0], _h2)

        @self.r.route("GET", "/api/ping", public=True)
        def ping(req):  # noqa: ANN001, ANN202
            return "pong"

        found = self.r.match("GET", "/api/ping")
        assert found is not None
        self.assertIs(found[0], ping)
        self.assertEqual(found[2], {"public": True})

    def test_param_does_not_cross_slash_and_is_anchored(self) -> None:
        self.assertIsNone(self.r.match("GET", "/api/records/a/b"))
        self.assertIsNone(self.r.match("GET", "/api/records/"))
        self.assertIsNone(self.r.match("GET", "/x/api/records/f-1"))
        self.assertIsNone(self.r.match("GET", "/api/records/f-1/"))
        self.assertIsNone(self.r.match("GET", "/api/nothing"))

    def test_405_when_path_exists_for_other_method(self) -> None:
        with self.assertRaises(HttpError) as cm:
            self.r.match("PUT", "/api/records/f-1")
        self.assertEqual(cm.exception.status, 405)
        self.assertEqual(cm.exception.code, "method_not_allowed")
        with self.assertRaises(HttpError):
            self.r.match("GET", "/api/records/f-1/correct")

    def test_real_api_router(self) -> None:
        from okura_web import api

        found = api.router.match("GET", "/api/status")
        assert found is not None
        self.assertIs(found[0], api.status)
        self.assertTrue(found[2].get("public"))
        with self.assertRaises(HttpError) as cm:
            api.router.match("DELETE", "/api/status")
        self.assertEqual(cm.exception.status, 405)


if __name__ == "__main__":
    unittest.main()
