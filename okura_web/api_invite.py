"""回答の依頼（招待リンク）。アカウントのない家族に、その人あての質問をリンクで聞く。

- 依頼を作るのは画面の人（その人を管理する人・世帯の管理者）。リンクは1回だけ使え、期限付き・取り消せる。
- リンクを開いた端末を、その人の端末として登録する（guest_sessions）。端末でできるのは「自分あての質問を見る・答える」だけ。
  金額（ほかの人の数字）は見せない。
- 答えは判断台帳に「その人が決めた」（judged_by）として追記する。根拠に招待の ID を書く（メールや名前は台帳に書かない）。
- 手前の認証（Access など）で確かめたメールがあれば、招待のメールと一致を求め、確かめたメールを招待の記録に残す。
  アプリは手前の認証の種類を知らない（proxyauth）。
"""

from __future__ import annotations

import re
from typing import Any

from . import db as dbm
from . import api
from .api import _access, _audit, _hh, _human, router, write_judgment
from .results import answer_template
from .server import HttpError, Request, Response, clear_guest_cookie, guest_cookie

_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,190}\.[A-Za-z]{2,24}$")
_QID = re.compile(r"^[^\x00-\x1f]{1,300}$")


def _not_guest(req: Request) -> None:
    _human(req)
    if req.principal is not None and req.principal.kind == "guest":
        raise HttpError(403, "招待リンクの端末では使えない", code="guest_only")


def _status(row: dict[str, Any], now: str) -> str:
    if row["revoked_at"]:
        return "revoked"
    if row["claimed_at"]:
        return "claimed"
    if row["expires_at"] < now:
        return "expired"
    return "pending"


def _guest_questions(hid: str, person: str, only: list[str]) -> list[dict[str, Any]]:
    """その人あての「選んで答える」質問だけ。金額（affects）は外す。"""
    lr = api.APP.latest_result(hid)
    if not lr:
        return []
    d = api.APP.load_digest(hid, lr["result_hash"])
    out = []
    for q in d.get("questions", []):
        if q.get("means") != "判断" or not q.get("candidates") or person not in (q.get("persons") or []):
            continue
        if only and q["id"] not in only:
            continue
        out.append({k: q.get(k) for k in ("id", "means", "kind", "candidates", "target", "persons", "years")})
    return out


# ---------------------------------------------------------------------------- 依頼する側（画面の人）
@router.route("POST", "/api/invites")
def create_invite(req: Request) -> Any:
    _not_guest(req)
    hid = _hh(req)
    acc = _access(req)
    p = req.principal
    assert p is not None
    b = req.json()
    person = str(b.get("person_id") or "")
    if person not in acc.all_persons:
        raise HttpError(400, "家族にいない人", code="bad_person")
    if person in acc.account_persons:
        raise HttpError(400, "この人はアカウントがあるので、ログインして答えてもらう", code="has_account")
    if not (acc.is_mine(person) or p.role == "admin"):
        raise HttpError(403, "依頼できるのは、その人を管理する人・世帯の管理者", code="forbidden")
    email = (b.get("email") or "").strip().lower() or None
    if email is not None and not _EMAIL.match(email):
        raise HttpError(400, "メールアドレスの形が違う", code="bad_email")
    qids = b.get("question_ids") or []
    if not isinstance(qids, list) or len(qids) > 100 or not all(isinstance(q, str) and _QID.match(q) for q in qids):
        raise HttpError(400, "question_ids の形が違う", code="bad_questions")
    days = b.get("days", 7)
    if not isinstance(days, int) or isinstance(days, bool):
        raise HttpError(400, "days は整数", code="bad_days")
    iid, token = api.APP.auth.create_invite(hid, person, p.user_id, email=email, question_ids=qids, days=days)
    _audit(req, "invite_created", iid)
    row = api.APP.db.one("SELECT expires_at FROM invites WHERE id=?", (iid,))
    return {"ok": True, "id": iid, "path": f"/join/{token}", "expires_at": row["expires_at"] if row else None}


@router.route("GET", "/api/invites")
def list_invites(req: Request) -> Any:
    _not_guest(req)
    hid = _hh(req)
    acc = _access(req)
    p = req.principal
    assert p is not None
    t = dbm.now_iso()
    names = {r["person_id"]: r["display_name"] for r in api.APP.db.all("SELECT person_id, display_name FROM persons WHERE household_id=?", (hid,))}
    users = {r["id"]: r["display_name"] for r in api.APP.db.all("SELECT id, display_name FROM users")}
    out = []
    for r in api.APP.db.all("SELECT * FROM invites WHERE household_id=? ORDER BY created_at DESC LIMIT 200", (hid,)):
        if not (p.role == "admin" or r["created_by"] == p.user_id or acc.is_mine(r["person_id"])):
            continue
        answers = api.APP.db.one("SELECT COUNT(*) AS n FROM audit WHERE action=? ", (f"guest_answered:{r['id']}",))
        out.append({
            "id": r["id"], "person_id": r["person_id"], "person": names.get(r["person_id"]),
            "email": r["email"], "questions": len([q for q in (r["question_ids"] or "").split(",") if q]),
            "created_by": users.get(r["created_by"]), "created_at": r["created_at"], "expires_at": r["expires_at"],
            "claimed_at": r["claimed_at"], "claimed_email": r["claimed_email"], "status": _status(dict(r), t),
            "answers": answers["n"] if answers else 0,
        })
    return {"invites": out}


@router.route("POST", "/api/invites/{iid}/revoke")
def revoke_invite(req: Request) -> Any:
    _not_guest(req)
    hid = _hh(req)
    acc = _access(req)
    p = req.principal
    assert p is not None
    row = api.APP.db.one("SELECT * FROM invites WHERE id=? AND household_id=?", (req.params["iid"], hid))
    if row is None:
        raise HttpError(404, "依頼がない", code="not_found")
    if not (p.role == "admin" or row["created_by"] == p.user_id or acc.is_mine(row["person_id"])):
        raise HttpError(403, "取り消せない", code="forbidden")
    api.APP.auth.revoke_invite(hid, row["id"])
    _audit(req, "invite_revoked", row["id"])
    return {"ok": True}


# ---------------------------------------------------------------------------- 答える側（招待リンクの端末）
@router.route("POST", "/api/join", public=True, no_csrf=True)
def join(req: Request) -> Any:
    token = str(req.json().get("token") or "")
    verified = getattr(req.handler, "proxy_email", None)
    r = api.APP.auth.claim_invite(token, verified)
    if isinstance(r, str):
        raise HttpError(400, r, code="invite_unusable")
    device, csrf, inv = r
    api.APP.db.audit(inv["household_id"], f"guest:{inv['id']}", "invite_claimed", inv["id"])
    resp = Response.json({"ok": True, "csrf": csrf})
    resp.headers["Set-Cookie"] = guest_cookie(device, api.APP.auth.GUEST_DAYS * 86400)
    return resp


@router.route("GET", "/api/guest/me", guest_ok=True)
def guest_me(req: Request) -> Any:
    p = req.principal
    if p is None or p.kind != "guest":
        raise HttpError(401, "招待リンクの端末ではない", code="not_guest")
    hid = _hh(req)
    qs = _guest_questions(hid, p.person_id or "", p.extra.get("question_ids") or [])
    involved = {x for q in qs for x in (q.get("persons") or [])} | {p.person_id}
    names = {r["person_id"]: r["display_name"] for r in api.APP.db.all("SELECT person_id, display_name FROM persons WHERE household_id=?", (hid,))}
    hh = api.APP.db.one("SELECT name FROM households WHERE id=?", (hid,))
    inv = api.APP.db.one("SELECT i.created_by, u.display_name FROM invites i LEFT JOIN users u ON u.id=i.created_by WHERE i.id=?", (p.extra.get("invite_id"),))
    return {
        "person": {"person_id": p.person_id, "display_name": p.display_name},
        "household": hh["name"] if hh else "",
        "from": inv["display_name"] if inv else "",
        "csrf": p.csrf,
        "persons": [{"person_id": x, "display_name": names.get(x, "")} for x in sorted(x for x in involved if x)],
        "questions": qs,
    }


@router.route("POST", "/api/guest/answer", guest_ok=True)
def guest_answer(req: Request) -> Any:
    p = req.principal
    if p is None or p.kind != "guest":
        raise HttpError(401, "招待リンクの端末ではない", code="not_guest")
    hid = _hh(req)
    b = req.json()
    qid, cand = str(b.get("question_id") or ""), b.get("candidate")
    q = next((x for x in _guest_questions(hid, p.person_id or "", p.extra.get("question_ids") or []) if x["id"] == qid), None)
    if q is None:
        raise HttpError(404, "その質問はない（もう決まったかもしれない）", code="not_found")
    if str(cand) not in [str(c) for c in q["candidates"]]:
        raise HttpError(400, "選べない答え", code="bad_candidate")
    t = answer_template(q, api.APP.meta(), str(cand))
    if t is None:
        raise HttpError(400, "この質問はリンクから答えられない", code="no_template")
    note = str(b.get("note") or "").strip()[:500]
    basis = f"本人が招待リンク（{p.extra.get('invite_id')}）で回答" + (f"：{note}" if note else "")
    out = write_judgment(req, t["section"], t["record"], basis)
    _audit(req, f"guest_answered:{p.extra.get('invite_id')}", out.get("record_id"))
    return {"ok": True}


@router.route("POST", "/api/guest/leave", guest_ok=True)
def guest_leave(req: Request) -> Any:
    resp = Response.json({"ok": True})
    resp.headers["Set-Cookie"] = clear_guest_cookie()
    return resp
