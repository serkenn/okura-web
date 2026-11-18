"""手前の認証の JWT の検証（proxyauth.ProxyAuthVerifier）。Cloudflare Access の書き方と汎用の書き方。鍵はテストの中で作る。ネットワークは使わない。"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import tempfile
import time
import unittest
from pathlib import Path

from okura_web.proxyauth import _SHA256_PREFIX, ProxyAuthVerifier


def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(16):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits: int) -> int:
    while True:
        c = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if _is_prime(c):
            return c


def _keypair() -> tuple[int, int, int]:
    e = 65537
    while True:
        p, q = _prime(512), _prime(512)
        phi = (p - 1) * (q - 1)
        if p != q and phi % e:
            return p * q, e, pow(e, -1, phi)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _sign(n: int, d: int, header: dict, claims: dict) -> str:
    h, p = _b64(json.dumps(header).encode()), _b64(json.dumps(claims).encode())
    k = (n.bit_length() + 7) // 8
    digest = hashlib.sha256(f"{h}.{p}".encode()).digest()
    em = b"\x00\x01" + b"\xff" * (k - 3 - len(_SHA256_PREFIX) - len(digest)) + b"\x00" + _SHA256_PREFIX + digest
    sig = pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")
    return f"{h}.{p}.{_b64(sig)}"


TEAM = "kakuu-family.cloudflareaccess.com"
AUD = "aud-kakuu-0001"


class AccessVerifierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.n, cls.e, cls.d = _keypair()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "cf-access.json"
        self.v = ProxyAuthVerifier(Path(self.tmp.name))
        self.v._keys = {"k1": (self.n, self.e)}
        self.v._keys_at = time.time()
        self.v._keys_url = f"https://{TEAM}/cdn-cgi/access/certs"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_cfg(self) -> None:
        # PowerShell の Set-Content -Encoding UTF8 は BOM を付ける
        self.cfg.write_bytes(b"\xef\xbb\xbf" + json.dumps({"team_domain": TEAM, "aud": AUD}).encode())

    def _claims(self, **over) -> dict:
        now = int(time.time())
        c = {"aud": [AUD], "exp": now + 600, "nbf": now - 10, "iss": f"https://{TEAM}", "email": "kakuu@example.invalid"}
        c.update(over)
        return c

    def test_fails_closed_without_config(self) -> None:
        ok, why, _ = self.v.verify(_sign(self.n, self.d, {"alg": "RS256", "kid": "k1"}, self._claims()))
        self.assertFalse(ok)
        self.assertIn("設定", why)

    def test_valid_token(self) -> None:
        self._write_cfg()
        ok, why, claims = self.v.verify(_sign(self.n, self.d, {"alg": "RS256", "kid": "k1"}, self._claims()))
        self.assertTrue(ok, why)
        self.assertEqual(claims["email"], "kakuu@example.invalid")
        self.assertEqual(self.v.email_of(claims), "kakuu@example.invalid")
        cfg = self.v.config()
        self.assertEqual((cfg.header, cfg.cookie), ("Cf-Access-Jwt-Assertion", "CF_Authorization"))
        self.assertEqual(cfg.jwks_url, f"https://{TEAM}/cdn-cgi/access/certs")

    def test_generic_config_any_provider(self) -> None:
        # Cloudflare 以外（例：Authelia・Pomerium）も、公開鍵の場所・発行元・宛先・ヘッダーの設定だけで使える
        iss = "https://auth.kakuu.example.invalid"
        (Path(self.tmp.name) / "proxy-auth.json").write_text(json.dumps({
            "jwks_url": f"{iss}/jwks.json", "issuer": iss, "audience": "okura-kakuu", "header": "X-Auth-Jwt", "email_claim": "mail",
        }), encoding="utf-8")
        self._write_cfg()  # 汎用の設定が優先
        now = int(time.time())
        tok = _sign(self.n, self.d, {"alg": "RS256", "kid": "k1"}, {"aud": "okura-kakuu", "iss": iss, "exp": now + 60, "mail": "Kakuu@Example.invalid"})
        self.v._keys_url = f"{iss}/jwks.json"
        ok, why, claims = self.v.verify(tok)
        self.assertTrue(ok, why)
        self.assertEqual(self.v.email_of(claims), "kakuu@example.invalid")
        self.assertEqual(self.v.token_from({"X-Auth-Jwt": tok}, {}), tok)
        # Cloudflare の発行元のトークンは通らない
        self.assertFalse(self.v.verify(_sign(self.n, self.d, {"alg": "RS256", "kid": "k1"}, self._claims()))[0])

    def test_generic_config_requires_https_jwks(self) -> None:
        (Path(self.tmp.name) / "proxy-auth.json").write_text(json.dumps({
            "jwks_url": "http://insecure.invalid/jwks", "issuer": "x", "audience": "y", "header": "X-Auth-Jwt",
        }), encoding="utf-8")
        self.assertIsNone(self.v.config())

    def test_rejects_missing_bad_and_tampered(self) -> None:
        self._write_cfg()
        good = _sign(self.n, self.d, {"alg": "RS256", "kid": "k1"}, self._claims())
        h, p, s = good.split(".")
        tampered = f"{h}.{_b64(json.dumps(self._claims(email='other@example.invalid')).encode())}.{s}"
        for tok in (None, "", "abc", tampered):
            with self.subTest(tok=str(tok)[:20]):
                self.assertFalse(self.v.verify(tok)[0])

    def test_rejects_wrong_aud_expired_issuer_alg_kid(self) -> None:
        self._write_cfg()
        cases = [
            ({"alg": "RS256", "kid": "k1"}, self._claims(aud=["other-aud"])),
            ({"alg": "RS256", "kid": "k1"}, self._claims(exp=int(time.time()) - 3600)),
            ({"alg": "RS256", "kid": "k1"}, self._claims(iss="https://evil.cloudflareaccess.com")),
            ({"alg": "HS256", "kid": "k1"}, self._claims()),
        ]
        for header, claims in cases:
            with self.subTest(header=header, claims=claims):
                self.assertFalse(self.v.verify(_sign(self.n, self.d, header, claims))[0])
        # 知らない鍵（取り直しは鍵の表を差し替えて止める）
        tok = _sign(self.n, self.d, {"alg": "RS256", "kid": "k-unknown"}, self._claims())
        self.v._fetch_keys = lambda url: {"k1": (self.n, self.e)}  # type: ignore[method-assign]
        self.assertFalse(self.v.verify(tok)[0])


if __name__ == "__main__":
    unittest.main()
