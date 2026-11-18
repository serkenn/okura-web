"""手前の認証（リバースプロキシ）が付けた JWT を確かめる（二重の守り。標準ライブラリだけ）。

アプリは特定の会社に依存しない。手前に置く認証（Cloudflare Access・Authelia・Authentik・Pomerium・oauth2-proxy など）が
付ける「署名付きの本人の証明（JWT、RS256）」を、設定した公開鍵の場所・発行元・宛先で検証するだけ。

設定（どちらか。上が優先）：
- `.work/proxy-auth.json`：汎用
    {"jwks_url": "https://…/certs", "issuer": "https://…", "audience": "…",
     "header": "X-…-Jwt", "cookie": "…"（任意）, "email_claim": "email"（任意）}
- `.work/cf-access.json`：Cloudflare Access の書き方（team_domain と aud から上の値を作る）

公開のホスト名（--public-host）で来たリクエストだけが対象。設定がない間は、公開のホスト名からのリクエストを全部断る（閉じた側に倒す）。
127.0.0.1 からの直接のリクエスト（この PC のブラウザ・MCP のサーバー）は対象外。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# SHA-256 の DigestInfo（PKCS#1 v1.5 の署名の中身の前置き）
_SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def _b64url(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@dataclass
class ProxyAuthConfig:
    jwks_url: str
    issuer: str
    audience: str
    header: str
    cookie: str | None = None
    email_claim: str = "email"
    name: str = "手前の認証"

    @classmethod
    def load(cls, work_dir: Path) -> "ProxyAuthConfig | None":
        generic = work_dir / "proxy-auth.json"
        if generic.exists():
            try:
                d = json.loads(generic.read_text(encoding="utf-8-sig"))
                if all(isinstance(d.get(k), str) and d[k] for k in ("jwks_url", "issuer", "audience", "header")):
                    if not d["jwks_url"].startswith("https://"):
                        return None
                    return cls(
                        d["jwks_url"], d["issuer"], d["audience"], d["header"],
                        d.get("cookie") or None, d.get("email_claim") or "email", d.get("name") or "手前の認証",
                    )
            except (OSError, ValueError):
                pass
            return None
        cf = work_dir / "cf-access.json"
        try:
            d = json.loads(cf.read_text(encoding="utf-8-sig"))
            if d.get("team_domain") and d.get("aud"):
                team = str(d["team_domain"]).removeprefix("https://").rstrip("/")
                return cls(
                    f"https://{team}/cdn-cgi/access/certs", f"https://{team}", str(d["aud"]),
                    "Cf-Access-Jwt-Assertion", "CF_Authorization", "email", "Cloudflare Access",
                )
        except (OSError, ValueError):
            pass
        return None


class ProxyAuthVerifier:
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self._keys: dict[str, tuple[int, int]] = {}
        self._keys_at = 0.0
        self._keys_url = ""
        self._lock = threading.Lock()

    def config(self) -> ProxyAuthConfig | None:
        return ProxyAuthConfig.load(self.work_dir)

    def _fetch_keys(self, url: str) -> dict[str, tuple[int, int]]:
        with self._lock:
            if self._keys and self._keys_url == url and time.time() - self._keys_at < 3600:
                return self._keys
            with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310 - 公開鍵だけ（家族のデータは送らない）
                data = json.loads(r.read(1_000_000).decode("utf-8"))
            keys = {}
            for k in data.get("keys", []):
                if k.get("kty") == "RSA" and k.get("kid"):
                    keys[k["kid"]] = (int.from_bytes(_b64url(k["n"]), "big"), int.from_bytes(_b64url(k["e"]), "big"))
            self._keys, self._keys_at, self._keys_url = keys, time.time(), url
            return keys

    def token_from(self, headers: Any, cookies: dict[str, str]) -> str | None:
        cfg = self.config()
        if cfg is None:
            return None
        return headers.get(cfg.header) or (cookies.get(cfg.cookie) if cfg.cookie else None)

    def verify(self, token: str | None) -> tuple[bool, str, dict[str, Any] | None]:
        """(通すか, 理由, クレーム)。"""
        cfg = self.config()
        if cfg is None:
            return False, "手前の認証の設定がまだない", None
        if not token or token.count(".") != 2:
            return False, f"{cfg.name} のトークンがない", None
        try:
            h64, p64, s64 = token.split(".")
            header = json.loads(_b64url(h64))
            claims = json.loads(_b64url(p64))
            sig = _b64url(s64)
        except (ValueError, json.JSONDecodeError):
            return False, "トークンの形が違う", None
        if header.get("alg") != "RS256":
            return False, "署名の方式が違う", None
        try:
            keys = self._fetch_keys(cfg.jwks_url)
        except OSError:
            return False, "公開鍵を取れない", None
        key = keys.get(header.get("kid", ""))
        if key is None:
            self._keys_at = 0.0  # 鍵の入れ替えに備えて次は取り直す
            return False, "知らない鍵", None
        n, e = key
        k = (n.bit_length() + 7) // 8
        em = pow(int.from_bytes(sig, "big"), e, n).to_bytes(k, "big")
        digest = hashlib.sha256(f"{h64}.{p64}".encode("ascii")).digest()
        expected = b"\x00\x01" + b"\xff" * (k - 3 - len(_SHA256_PREFIX) - len(digest)) + b"\x00" + _SHA256_PREFIX + digest
        if not hmac.compare_digest(em, expected):
            return False, "署名が合わない", None
        aud = claims.get("aud")
        auds = aud if isinstance(aud, list) else [aud]
        if cfg.audience not in auds:
            return False, "対象のアプリが違う", None
        now = time.time()
        if float(claims.get("exp", 0)) < now - 30 or float(claims.get("nbf", 0)) > now + 30:
            return False, "トークンの期限が切れている", None
        if claims.get("iss") != cfg.issuer:
            return False, "発行元が違う", None
        return True, "ok", claims

    def email_of(self, claims: dict[str, Any] | None) -> str | None:
        cfg = self.config()
        if not claims or cfg is None:
            return None
        v = claims.get(cfg.email_claim)
        return v.strip().lower() if isinstance(v, str) and "@" in v else None
