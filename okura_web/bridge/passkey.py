"""パスキー（WebAuthn）の検証。.work/venvs/auth の Python で、サブプロセスとして動かす（Web のサーバーは webauthn を import しない）。

標準入力：{"op": ..., ...} → 標準出力：結果の JSON。誤りは {"ok": false, "error": "<種類>"}（例外の文は出さない）で終了コード 2。
challenge・origin・RP ID は呼ぶ側（サーバー）が決めて渡す。リクエストのヘッダーからは取らない。ユーザーの確認（UV）は必須。
"""

import base64
import json
import sys

if not sys.flags.isolated:
    print(json.dumps({"ok": False, "error": "launch"}))
    sys.exit(4)

from webauthn import (  # noqa: E402
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (  # noqa: E402
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)


def b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def main() -> int:
    raw = sys.stdin.buffer.read(256 * 1024)
    req = json.loads(raw.decode("utf-8"))
    op = req.get("op")
    if op == "register_options":
        opts = generate_registration_options(
            rp_id=req["rp_id"],
            rp_name=req["rp_name"],
            user_id=b64d(req["user_handle"]),
            user_name=req["user_name"],
            user_display_name=req["user_name"],
            challenge=b64d(req["challenge"]),
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.REQUIRED
            ),
            exclude_credentials=[PublicKeyCredentialDescriptor(id=b64d(x)) for x in req.get("exclude", [])],
            timeout=300000,
        )
        out = {"ok": True, "options": json.loads(options_to_json(opts))}
    elif op == "register_verify":
        v = verify_registration_response(
            credential=req["credential"],
            expected_challenge=b64d(req["challenge"]),
            expected_origin=req["origin"],
            expected_rp_id=req["rp_id"],
            require_user_verification=True,
        )
        out = {"ok": True, "credential_id": b64e(v.credential_id), "public_key": b64e(v.credential_public_key), "sign_count": v.sign_count}
    elif op == "login_options":
        opts = generate_authentication_options(
            rp_id=req["rp_id"], challenge=b64d(req["challenge"]), user_verification=UserVerificationRequirement.REQUIRED, timeout=300000
        )
        out = {"ok": True, "options": json.loads(options_to_json(opts))}
    elif op == "login_verify":
        v = verify_authentication_response(
            credential=req["credential"],
            expected_challenge=b64d(req["challenge"]),
            expected_origin=req["origin"],
            expected_rp_id=req["rp_id"],
            credential_public_key=b64d(req["public_key"]),
            credential_current_sign_count=int(req["sign_count"]),
            require_user_verification=True,
        )
        out = {"ok": True, "sign_count": v.new_sign_count}
    else:
        out = {"ok": False, "error": "op"}
    sys.stdout.write(json.dumps(out))
    return 0 if out.get("ok") else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 - 検証の失敗。種類だけを返す（例外の文は出さない）
        sys.stdout.write(json.dumps({"ok": False, "error": type(e).__name__}))
        sys.exit(2)
