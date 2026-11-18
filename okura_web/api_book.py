"""家計簿の API。取得はしない（取得元が /api/v1/imports に送る）。登録（台帳への書き込み）は画面の人だけ。

画面の呼び名と型は docs/household-ui-references.md（マネーフォワード ME・Zaim・freee などに合わせる）。

- 取り込み（POST /api/v1/imports）：エージェントのトークン（scope import）か画面の人。**登録待ち** に置くだけ。
  同じ取得元・同じ取得元の ID は二度入らない（台帳・登録待ち・対象外のどれにあっても）。
- 登録待ちの **登録**（1件・まとめて）・**対象外**・戻す、手で **入力**・直す・取り消す：画面の人だけ（招待リンクの端末・エージェントは不可）。
- 見える範囲は **口座ごと**：共有（家族のだれでも見える）か **自分だけ**（持ち主と、その人を管理する人だけ。合計にも入れない）。
  新しい口座は自分だけ。編集は持ち主・その人を管理する人・世帯の管理者（見える口座だけ）。取引は、その取引の口座が全部見えるときだけ見える。
- **計算対象外** の取引と **振替**（口座どうしの移動）は収支に入れない。
- 法令の判断はしない。カテゴリの「関係しうる書類」（hint）は見返す目印だけ（控除になるか・いくらかは判定コアと人が決める）。
"""

from __future__ import annotations

import calendar
import datetime as _dt
import hashlib
import json
import re
import secrets
from typing import Any

from . import api
from . import db as dbm
from .access import Access
from .api import _access, _audit, _hh, _human, router
from .book import ACCOUNT_RE, SOURCE_RE, BookError, BookState, balance_checks, clean_text, new_tx_id, valid_date
from .server import HttpError, Request

ASSET_KINDS = {"bank": "Assets:Bank", "card": "Liabilities:Card", "emoney": "Assets:EMoney", "cash": "Assets:Cash", "securities": "Assets:Securities", "other": "Assets:Other"}
CATEGORY_KINDS = ("expense", "income")
UNCATEGORIZED = {"expense": "Expenses:Uncategorized", "income": "Income:Uncategorized"}
UNKNOWN = "Expenses:Other:Unknown"  # 使途不明金（残高を調整したときの差額）
MAX_IMPORT = 2000
MAX_REGISTER = 100
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# 既定のカテゴリ（docs/household-ui-references.md §2：MF の大項目の名前 ＋ Zaim の内訳）。勘定の名前は英数字。
# (大項目の勘定, 名前, アイコン, [(中項目, 名前, 関係しうる書類の目印)])
EXPENSES: list[tuple[str, str, str, list[tuple[str, str, str]]]] = [
    ("Food", "食費", "utensils", [("Groceries", "食料品", ""), ("DiningOut", "外食", ""), ("Cafe", "カフェ", "")]),
    ("Daily", "日用品", "basket", [("Supplies", "消耗品", ""), ("Kids", "子ども", ""), ("Pets", "ペット", "")]),
    ("Transport", "交通費", "train", [("Train", "電車", ""), ("Bus", "バス", ""), ("Taxi", "タクシー", ""), ("Flight", "飛行機", "")]),
    ("Hobby", "趣味・娯楽", "gamepad", [("Leisure", "レジャー", ""), ("Books", "本", ""), ("Music", "音楽", ""), ("Movies", "映画", ""), ("Games", "ゲーム", "")]),
    ("Social", "交際費", "gift", [("Drinks", "飲み会", ""), ("Gifts", "プレゼント", ""), ("Celebration", "ご祝儀", ""), ("Condolence", "香典", "")]),
    ("Clothing", "衣服・美容", "shirt", [("Clothes", "洋服", ""), ("Hair", "美容院", ""), ("Cosmetics", "コスメ", ""), ("Cleaning", "クリーニング", "")]),
    ("Medical", "健康・医療", "heart", [("Hospital", "病院代", "医療費"), ("Drugs", "薬代", "医療費"), ("Gym", "ジム", "")]),
    ("Insurance", "保険", "shield", [("Life", "生命保険", "生命保険料"), ("Health", "医療保険", "生命保険料"), ("Earthquake", "地震保険", "地震保険料"), ("Fire", "火災保険", "")]),
    ("Education", "教養・教育", "book", [("Tuition", "学費", ""), ("Cram", "塾", ""), ("Lessons", "習い事", ""), ("Textbooks", "参考書", ""), ("Exams", "受験料", "")]),
    ("Phone", "通信費", "phone", [("Mobile", "携帯電話", ""), ("Internet", "インターネット", ""), ("Postal", "郵便", "")]),
    ("Utilities", "水道・光熱費", "bulb", [("Water", "水道", ""), ("Electricity", "電気", ""), ("Gas", "ガス", "")]),
    ("Housing", "住宅", "home", [("Rent", "家賃", ""), ("Mortgage", "住宅ローン", "住宅ローン"), ("Furniture", "家具", ""), ("Appliances", "家電", "")]),
    ("Car", "自動車", "car", [("Fuel", "ガソリン", ""), ("Parking", "駐車場", ""), ("Insurance", "自動車保険", ""), ("Tax", "自動車税", ""), ("Tolls", "高速料金", "")]),
    ("Tax", "税・社会保障", "building", [("IncomeTax", "所得税", ""), ("ResidentTax", "住民税", ""), ("Pension", "国民年金", "社会保険料"),
                                      ("HealthInsurance", "国民健康保険", "社会保険料"), ("IDeCo", "iDeCo", "小規模企業共済等掛金"), ("MutualAid", "共済", "小規模企業共済等掛金")]),
    ("Special", "特別な支出", "star", [("Travel", "旅行", ""), ("Ceremony", "冠婚葬祭", ""), ("Childbirth", "出産", "医療費"), ("Care", "介護", "医療費"),
                                   ("Donation", "寄付・ふるさと納税", "寄附金")]),
    ("Other", "その他", "dots", [("Allowance", "お小遣い", ""), ("Unknown", "使途不明金", "")]),
    ("Uncategorized", "未分類", "question", []),
]
INCOMES: list[tuple[str, str, str, str]] = [
    ("Salary", "給与", "wallet", "源泉徴収票"), ("Bonus", "賞与", "wallet", "源泉徴収票"), ("Business", "事業・副業", "briefcase", "支払調書"),
    ("Pension", "年金", "wallet", "源泉徴収票"), ("Dividend", "配当", "chart", ""), ("Interest", "利子", "chart", ""),
    ("Windfall", "臨時収入", "gift", ""), ("Reimbursement", "立替金の返済", "arrows", ""), ("Other", "その他の入金", "dots", ""),
    ("Uncategorized", "未分類", "question", ""),
]


def _defaults() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, (code, label, icon, children) in enumerate(EXPENSES):
        top = f"Expenses:{code}"
        out.append({"account": top, "label": label, "kind": "expense", "icon": icon, "parent": None, "sort": i * 100, "hint": ""})
        for j, (cc, cl, hint) in enumerate(children):
            out.append({"account": f"{top}:{cc}", "label": cl, "kind": "expense", "icon": icon, "parent": top, "sort": i * 100 + j + 1, "hint": hint})
    for i, (code, label, icon, hint) in enumerate(INCOMES):
        out.append({"account": f"Income:{code}", "label": label, "kind": "income", "icon": icon, "parent": None, "sort": 5000 + i, "hint": hint})
    return out


DEFAULTS = _defaults()
HINTS = {d["account"]: d["hint"] for d in DEFAULTS if d["hint"]}


# ---------------------------------------------------------------------------- 共通
def _app():
    return api.APP


def _book(hid: str):
    return _app().book(hid)


def _human_only(req: Request) -> None:
    _human(req)
    if req.principal is not None and req.principal.kind == "guest":
        raise HttpError(403, "招待リンクの端末では使えない", code="guest_only")


def _book_error(e: BookError) -> HttpError:
    return HttpError(400, str(e), code=e.code, detail=e.problems[:20] or None)


def _accounts(hid: str) -> dict[str, dict[str, Any]]:
    rows = _app().db.all("SELECT * FROM book_accounts WHERE household_id=? ORDER BY sort, label", (hid,))
    return {r["account"]: dict(r) for r in rows}


def _ensure_defaults(hid: str, by: str) -> None:
    """カテゴリがまだなければ既定のものを作る（台帳に open を足す）。"""
    db = _app().db
    if db.one("SELECT 1 AS x FROM book_accounts WHERE household_id=? AND kind IN ('expense','income') LIMIT 1", (hid,)):
        return
    now = dbm.now_iso()
    with db.tx() as c:
        for d in DEFAULTS:
            c.execute(
                "INSERT OR IGNORE INTO book_accounts(household_id, account, label, kind, parent, icon, shared, sort, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (hid, d["account"], d["label"], d["kind"], d["parent"], d["icon"], 1, d["sort"], by, now),
            )
    book = _book(hid)
    st = book.state()
    opens = [{"op": "open", "account": d["account"]} for d in DEFAULTS if d["account"] not in st.accounts]
    if opens:
        book.append(opens, by=by)


def _visible_account(acc: Access, row: dict[str, Any] | None) -> bool:
    if row is None:
        return False
    if row["kind"] in CATEGORY_KINDS:
        return True
    owner = row.get("owner_person")
    return not owner or bool(row.get("shared")) or acc.is_mine(owner)


def _can_write_account(req: Request, acc: Access, row: dict[str, Any] | None) -> bool:
    if not _visible_account(acc, row):
        return False
    assert row is not None
    owner = row.get("owner_person")
    return not owner or acc.is_mine(owner) or (req.principal is not None and req.principal.role == "admin")


def _is_money(row: dict[str, Any] | None) -> bool:
    return row is not None and row["kind"] not in CATEGORY_KINDS


def _money_accounts(t: dict[str, Any], accts: dict[str, dict[str, Any]]) -> list[str]:
    return [p["account"] for p in t["postings"] if p["account"] not in accts or _is_money(accts[p["account"]])]


def _txn_visible(acc: Access, t: dict[str, Any], accts: dict[str, dict[str, Any]]) -> bool:
    return all(_visible_account(acc, accts.get(a)) for a in _money_accounts(t, accts))


def _txn_view(t: dict[str, Any], accts: dict[str, dict[str, Any]], links: dict[str, str] | None = None) -> dict[str, Any]:
    """画面に出す形：口座・カテゴリ（または振替先）・金額（口座から見た向き：支出は負、収入は正）。"""
    money = [p for p in t["postings"] if _is_money(accts.get(p["account"]))]
    cats = [p for p in t["postings"] if not _is_money(accts.get(p["account"]))]
    main = money[0] if money else t["postings"][0]
    transfer = not cats and len(money) >= 2
    other = money[1] if transfer else (cats[0] if cats else t["postings"][-1])
    owner = (accts.get(main["account"]) or {}).get("owner_person")
    return {
        "id": t["id"], "date": t["date"], "payee": t.get("payee") or "", "memo": t.get("memo") or t.get("narration") or "",
        "account": main["account"], "amount": main["amount"], "owner_person": owner,
        "category": None if transfer else other["account"], "transfer_to": other["account"] if transfer else None,
        "split": len(t["postings"]) > 2, "excluded": bool(t.get("excluded")), "imported": bool(t.get("source")),
        "parts": [{"category": c["account"], "amount": abs(c["amount"])} for c in cats] if len(cats) > 1 else None,
        "tax_record": (links or {}).get(t["id"]), "recurring": t.get("source") == "recurring",
    }


def _month_range(month: str) -> tuple[str, str]:
    y, m = int(month[:4]), int(month[5:7])
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y:04d}-{m:02d}-01", f"{ny:04d}-{nm:02d}-01"


def _today() -> str:
    return dbm.now_iso()[:10]


def _rules(hid: str) -> list[dict[str, Any]]:
    rows = _app().db.all("SELECT * FROM book_rules WHERE household_id=? AND retired_at IS NULL ORDER BY length(pattern) DESC, created_at DESC", (hid,))
    return [dict(r) for r in rows]


def _rule_for(rules: list[dict[str, Any]], payee: str, accts: dict[str, dict[str, Any]]) -> str | None:
    for r in rules:
        if r["pattern"] and r["pattern"] in (payee or "") and r["category"] in accts and not accts[r["category"]].get("retired_at"):
            return r["category"]
    return None


def _add_rule(hid: str, pattern: str, category: str, by: str) -> None:
    pattern = clean_text(pattern, 60)
    if not pattern:
        return
    with _app().db.tx() as c:
        c.execute("UPDATE book_rules SET retired_at=? WHERE household_id=? AND pattern=? AND retired_at IS NULL", (dbm.now_iso(), hid, pattern))
        c.execute("INSERT INTO book_rules(id, household_id, pattern, category, created_by, created_at) VALUES (?,?,?,?,?,?)",
                  (dbm.new_id("rule", 6), hid, pattern, category, by, dbm.now_iso()))


def _check_target(req: Request, acc: Access, accts: dict[str, dict[str, Any]], target: Any, account: str | None) -> str:
    """カテゴリか振替先の口座。"""
    row = accts.get(target) if isinstance(target, str) else None
    if row is None or row.get("retired_at") or target == account:
        raise HttpError(400, "カテゴリか振替先を選ぶ", code="bad_category")
    if _is_money(row) and not _can_write_account(req, acc, row):
        raise HttpError(403, "その口座への振替にはできない", code="forbidden")
    return str(target)


# ---------------------------------------------------------------------------- 取り込み（取得元 → 登録待ち）
@router.route("POST", "/api/v1/imports", token_ok=True)
def import_batch(req: Request) -> Any:
    p = req.principal
    assert p is not None
    if p.kind == "guest":
        raise HttpError(403, "招待リンクの端末では使えない", code="guest_only")
    if p.kind == "token" and "import" not in p.scopes:
        raise HttpError(403, "取り込みの権限（import）のトークンが要る", code="scope")
    hid = _hh(req)
    out = create_batch(hid, p.actor, p.person_id, req.json())
    if out.get("batch_id"):
        _audit(req, "book_import_received", out["batch_id"])
    return out


def create_batch(hid: str, actor: str, person_id: str | None, b: dict[str, Any]) -> dict[str, Any]:
    """取り込みのまとまりを登録待ちに置く（取得元の API と、アプリ内の AI の提案の両方から使う）。"""
    if not isinstance(b, dict):
        raise HttpError(400, "本体の形が違う", code="bad_body")
    source = b.get("source")
    if not isinstance(source, str) or not SOURCE_RE.match(source):
        raise HttpError(400, "source は英数字と _ . : - （64文字まで）", code="bad_source")
    a = b.get("account") or {}
    key = a.get("key")
    if not isinstance(key, str) or not SOURCE_RE.match(key):
        raise HttpError(400, "account.key は英数字と _ . : - （64文字まで）", code="bad_account")
    kind = a.get("kind") or "bank"
    if kind not in ASSET_KINDS:
        raise HttpError(400, f"account.kind は {', '.join(ASSET_KINDS)}", code="bad_account")
    # 新しい口座の持ち主は、トークン（またはログイン）の人。見える範囲は自分だけから始める
    info = {"key": key, "kind": kind, "label": clean_text(a.get("label"), 40) or key, "owner_person": person_id}
    txs = b.get("transactions") or []
    if not isinstance(txs, list) or len(txs) > MAX_IMPORT:
        raise HttpError(400, f"transactions は {MAX_IMPORT} 件まで", code="too_many")
    st: BookState = _book(hid).state()
    known = set()
    for r in _app().db.all("SELECT items FROM book_imports WHERE household_id=? AND source=?", (hid, source)):
        known.update(x["source_id"] for x in json.loads(r["items"]))
    items, dup = [], 0
    for i, t in enumerate(txs):
        if not isinstance(t, dict):
            raise HttpError(400, f"transactions[{i}] の形が違う", code="bad_txn")
        sid = t.get("id")
        if not isinstance(sid, str) or not 0 < len(sid) <= 200:
            raise HttpError(400, f"transactions[{i}].id（取得元での ID）が要る", code="bad_txn")
        sid = clean_text(sid, 200)
        amt = t.get("amount")
        if not valid_date(t.get("date")) or not isinstance(amt, int) or isinstance(amt, bool) or amt == 0 or abs(amt) > 10**12:
            raise HttpError(400, f"transactions[{i}]：date は YYYY-MM-DD、amount は 0 でない整数の円（入金は正、出金は負）", code="bad_txn")
        if (source, sid) in st.sources or sid in known:
            dup += 1
            continue
        known.add(sid)
        item = {"source_id": sid, "date": t["date"], "amount": amt, "payee": clean_text(t.get("payee"), 120),
                "memo": clean_text(t.get("memo"), 200), "state": "pending"}
        if isinstance(t.get("category"), str) and ACCOUNT_RE.match(t["category"]):
            item["suggested"] = t["category"]  # 取得元・AI の推測（登録待ちで人が確かめる）
        items.append(item)
    bal = b.get("balance")
    if bal is not None:
        if not isinstance(bal, dict) or not valid_date(bal.get("date")) or not isinstance(bal.get("amount"), int) or isinstance(bal.get("amount"), bool):
            raise HttpError(400, "balance は {date, amount（整数の円）}", code="bad_balance")
        bal = {"date": bal["date"], "amount": bal["amount"]}
        if not items:
            mapped = _app().db.one("SELECT account FROM book_accounts WHERE household_id=? AND source=? AND source_key=?", (hid, source, key))
            same = any(json.loads(r["balance"] or "null") == bal for r in _app().db.all(
                "SELECT balance FROM book_imports WHERE household_id=? AND source=? AND account_key=?", (hid, source, key)))
            if same or (mapped and {"account": mapped["account"], **bal} in st.balances):
                bal = None
    if not items and bal is None:
        return {"ok": True, "batch_id": None, "accepted": 0, "duplicates": dup}
    bid = dbm.new_id("imp", 6)
    with _app().db.tx() as c:
        c.execute(
            "INSERT INTO book_imports(id, household_id, source, account_key, account_info, items, balance, received_by, received_at, status) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (bid, hid, source, key, json.dumps(info, ensure_ascii=False), json.dumps(items, ensure_ascii=False),
             json.dumps(bal) if bal else None, actor, dbm.now_iso(), "pending"),
        )
    return {"ok": True, "batch_id": bid, "accepted": len(items), "duplicates": dup}


# ---------------------------------------------------------------------------- 登録待ち（人が登録する）
def _batch_account(row: dict[str, Any], accts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """取り込みのまとまりの口座。まだ口座がなければ、これから作る口座の形（account は None）。"""
    mapped = next((a for a in accts.values() if a.get("source") == row["source"] and a.get("source_key") == row["account_key"]), None)
    if mapped:
        return mapped
    info = json.loads(row["account_info"])
    return {"account": None, "label": info["label"], "kind": info["kind"], "owner_person": info.get("owner_person"), "shared": 0}


@router.route("GET", "/api/book/pending")
def list_pending(req: Request) -> Any:
    _human_only(req)
    hid = _hh(req)
    acc = _access(req)
    p = req.principal
    assert p is not None
    _ensure_defaults(hid, p.actor)
    state = "ignored" if req.arg("state") == "ignored" else "pending"
    accts = _accounts(hid)
    rules = _rules(hid)
    out = []
    for r in _app().db.all("SELECT * FROM book_imports WHERE household_id=? AND status='pending' ORDER BY received_at", (hid,)):
        row = dict(r)
        ba = _batch_account(row, accts)
        if not _visible_account(acc, ba):
            continue
        for it in json.loads(row["items"]):
            if it.get("state", "pending") != state:
                continue
            rule = _rule_for(rules, it["payee"], accts)
            guess = it.get("suggested") if (accts.get(it.get("suggested") or "") or {}).get("kind") in CATEGORY_KINDS else None
            sug = rule or guess
            out.append({"batch": row["id"], "source_id": it["source_id"], "date": it["date"], "amount": it["amount"], "payee": it["payee"],
                        "memo": it["memo"], "account": ba["account"], "account_label": ba["label"], "owner_person": ba.get("owner_person"),
                        "category": sug, "by_rule": bool(rule), "guessed": bool(guess and not rule), "received_at": row["received_at"]})
    out.sort(key=lambda x: (x["date"], x["source_id"]), reverse=True)
    return {"items": out}


def _decide(req: Request, items: Any, decide: str) -> dict[str, Any]:
    """登録待ちの行を登録（register）・対象外（ignore）・戻す（restore）。"""
    _human_only(req)
    hid = _hh(req)
    acc = _access(req)
    p = req.principal
    assert p is not None
    if not isinstance(items, list) or not 0 < len(items) <= MAX_REGISTER:
        raise HttpError(400, f"items は 1〜{MAX_REGISTER} 件", code="bad_items")
    _ensure_defaults(hid, p.actor)
    accts = _accounts(hid)
    by_batch: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        if not isinstance(it, dict) or not isinstance(it.get("batch"), str) or not isinstance(it.get("source_id"), str):
            raise HttpError(400, "items の形が違う", code="bad_items")
        by_batch.setdefault(it["batch"], []).append(it)
    events: list[dict[str, Any]] = []
    updates: list[tuple[str, list[dict[str, Any]], bool]] = []
    new_accounts: list[tuple[Any, ...]] = []
    rules_to_add: list[tuple[str, str]] = []
    st = _book(hid).state()
    now = dbm.now_iso()
    for bid, want in by_batch.items():
        r = _app().db.one("SELECT * FROM book_imports WHERE id=? AND household_id=? AND status='pending'", (bid, hid))
        if r is None:
            raise HttpError(404, "登録待ちがない（もう登録したかもしれない）", code="not_found")
        row = dict(r)
        ba = _batch_account(row, accts)
        if not _can_write_account(req, acc, ba):
            raise HttpError(403, "この口座の明細は登録できない", code="forbidden")
        account = ba["account"]
        if decide == "register" and account is None:
            info = json.loads(row["account_info"])
            account = f"{ASSET_KINDS[info['kind']]}:S{hashlib.sha256((row['source'] + '|' + row['account_key']).encode()).hexdigest()[:8]}"
            if account not in accts:
                new_accounts.append((hid, account, info["label"], info["kind"], info.get("owner_person"), 0, row["source"], row["account_key"], 100, p.actor, now))
                accts[account] = {"account": account, "kind": info["kind"], "owner_person": info.get("owner_person"), "shared": 0, "label": info["label"]}
            if account not in st.accounts and not any(e["op"] == "open" and e["account"] == account for e in events):
                events.append({"op": "open", "account": account})
        all_items = json.loads(row["items"])
        idx = {x["source_id"]: x for x in all_items}
        for w in want:
            it = idx.get(w["source_id"])
            if it is None:
                raise HttpError(404, "その明細がない", code="not_found")
            cur = it.get("state", "pending")
            if decide == "restore":
                if cur != "ignored":
                    continue
                it["state"] = "pending"
            elif cur != "pending":
                continue
            elif decide == "ignore":
                it["state"] = "ignored"
            else:
                target = _check_target(req, acc, accts, w.get("category") or UNCATEGORIZED["income" if it["amount"] > 0 else "expense"], account)
                if (row["source"], it["source_id"]) not in st.sources:
                    events.append({"op": "add", "txn": {
                        "id": new_tx_id(f"{hid}|{row['source']}|{it['source_id']}|{secrets.token_hex(4)}"), "date": it["date"], "payee": it["payee"], "narration": it["memo"],
                        "source": row["source"], "source_id": it["source_id"],
                        "postings": [{"account": account, "amount": it["amount"]}, {"account": target, "amount": -it["amount"]}],
                    }})
                    if w.get("remember") and it["payee"]:
                        rules_to_add.append((it["payee"], target))
                it["state"] = "registered"
            it["decided_by"], it["decided_at"] = p.actor, now
        done = all(x.get("state") in ("registered", "ignored") for x in all_items)
        if done and row["balance"] and account:
            bal = json.loads(row["balance"])
            events.append({"op": "balance", "account": account, "date": bal["date"], "amount": bal["amount"]})
        updates.append((bid, all_items, done))
    if new_accounts:
        with _app().db.tx() as c:
            c.executemany(
                "INSERT OR IGNORE INTO book_accounts(household_id, account, label, kind, owner_person, shared, source, source_key, sort, created_by, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)", new_accounts)
    if events:
        try:
            _book(hid).append(events, by=p.actor)
        except BookError as e:
            raise _book_error(e) from e
    for pattern, target in rules_to_add:
        _add_rule(hid, pattern, target, p.actor)
    with _app().db.tx() as c:
        for bid, all_items, done in updates:
            c.execute("UPDATE book_imports SET items=?, status=?, decided_by=?, decided_at=? WHERE id=?",
                      (json.dumps(all_items, ensure_ascii=False), "confirmed" if done else "pending", p.actor if done else None, now if done else None, bid))
    _audit(req, f"book_pending_{decide}", ",".join(by_batch))
    return {"ok": True, "added": sum(1 for e in events if e["op"] == "add")}


@router.route("POST", "/api/book/pending/register")
def register_pending(req: Request) -> Any:
    return _decide(req, req.json().get("items"), "register")


@router.route("POST", "/api/book/pending/ignore")
def ignore_pending(req: Request) -> Any:
    return _decide(req, req.json().get("items"), "ignore")


@router.route("POST", "/api/book/pending/restore")
def restore_pending(req: Request) -> Any:
    return _decide(req, req.json().get("items"), "restore")


# ---------------------------------------------------------------------------- 口座・カテゴリ・分類ルール
@router.route("GET", "/api/book/accounts")
def list_accounts(req: Request) -> Any:
    _human_only(req)
    hid = _hh(req)
    acc = _access(req)
    p = req.principal
    assert p is not None
    _ensure_defaults(hid, p.actor)
    accts = _accounts(hid)
    st = _book(hid).state()
    checks = {c["account"]: c for c in balance_checks(st)}
    bal: dict[str, int] = {}
    for t in st.txns.values():
        for q in t["postings"]:
            bal[q["account"]] = bal.get(q["account"], 0) + q["amount"]
    last: dict[tuple[str, str], str] = {}
    for r in _app().db.all("SELECT source, account_key, MAX(received_at) AS t FROM book_imports WHERE household_id=? GROUP BY source, account_key", (hid,)):
        last[(r["source"], r["account_key"])] = r["t"]
    out_acc, out_cat = [], []
    for a in accts.values():
        if a.get("retired_at") or not _visible_account(acc, a):
            continue
        view = {"account": a["account"], "label": a["label"], "kind": a["kind"], "icon": a.get("icon"), "parent": a.get("parent"),
                "owner_person": a.get("owner_person"), "shared": bool(a.get("shared")) or not a.get("owner_person"),
                "hidden": bool(a.get("hidden")), "can_edit": _can_write_account(req, acc, a), "hint": HINTS.get(a["account"], "")}
        if a["kind"] in CATEGORY_KINDS:
            out_cat.append(view)
        else:
            chk = checks.get(a["account"])
            view["balance"] = bal.get(a["account"], 0)
            view["check"] = {"date": chk["date"], "ok": chk["ok"], "reported": chk["amount"]} if chk else None
            view["last_import"] = last.get((a.get("source") or "", a.get("source_key") or ""))
            out_acc.append(view)
    return {"accounts": out_acc, "categories": out_cat}


@router.route("POST", "/api/book/accounts")
def add_account(req: Request) -> Any:
    """口座（財布など）か、中項目のカテゴリを足す。"""
    _human_only(req)
    hid = _hh(req)
    acc = _access(req)
    p = req.principal
    assert p is not None
    _ensure_defaults(hid, p.actor)
    b = req.json()
    kind = b.get("kind")
    label = clean_text(b.get("label"), 40)
    if not label:
        raise HttpError(400, "名前が要る", code="bad_label")
    owner, shared, parent, icon = None, 1, None, clean_text(b.get("icon"), 30) or None
    if kind in ASSET_KINDS:
        owner = b.get("owner_person", p.person_id)
        if owner is not None and owner not in acc.all_persons:
            raise HttpError(400, "家族にいない人", code="bad_person")
        if owner and not (acc.is_mine(owner) or p.role == "admin"):
            raise HttpError(403, "この人の口座は作れない", code="forbidden")
        shared = 1 if (b.get("shared") or not owner) else 0
        base = ASSET_KINDS[kind]
    elif kind in CATEGORY_KINDS:
        accts = _accounts(hid)
        parent = b.get("parent")
        prow = accts.get(parent) if parent else None
        if parent is not None and (prow is None or prow["kind"] != kind or prow.get("parent")):
            raise HttpError(400, "親のカテゴリ（大項目）を選ぶ", code="bad_parent")
        base = parent or ("Expenses" if kind == "expense" else "Income")
        icon = icon or (prow or {}).get("icon")
    else:
        raise HttpError(400, "kind が違う", code="bad_kind")
    name = f"{base}:C{secrets.token_hex(4)}"
    if not ACCOUNT_RE.match(name):
        raise HttpError(400, "これ以上深いカテゴリは作れない", code="too_deep")
    with _app().db.tx() as c:
        c.execute(
            "INSERT INTO book_accounts(household_id, account, label, kind, parent, icon, owner_person, shared, sort, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (hid, name, label, kind, parent, icon, owner, shared, 9000, p.actor, dbm.now_iso()),
        )
    try:
        _book(hid).append([{"op": "open", "account": name}], by=p.actor)
    except BookError as e:
        raise _book_error(e) from e
    _audit(req, "book_account_added", name)
    return {"ok": True, "account": name}


@router.route("POST", "/api/book/accounts/{name}/update")
def update_account(req: Request) -> Any:
    """名前・共有／自分だけ・持ち主・隠す。変えた人と日時は操作の記録に残す。"""
    _human_only(req)
    hid = _hh(req)
    acc = _access(req)
    p = req.principal
    assert p is not None
    accts = _accounts(hid)
    row = accts.get(req.params["name"])
    if row is None or not _visible_account(acc, row):
        raise HttpError(404, "口座・カテゴリがない", code="not_found")
    b = req.json()
    sets: dict[str, Any] = {}
    if row["kind"] in CATEGORY_KINDS:
        if p.role != "admin" and row["created_by"] != p.actor:
            raise HttpError(403, "カテゴリを変えられるのは作った人・世帯の管理者", code="forbidden")
        if "hidden" in b:
            sets["hidden"] = 1 if b["hidden"] else 0
    else:
        if not _can_write_account(req, acc, row):
            raise HttpError(403, "この口座は変えられない", code="forbidden")
        if "shared" in b:
            if row.get("owner_person") and not (acc.is_mine(row["owner_person"]) or p.role == "admin"):
                raise HttpError(403, "共有するかを決めるのは持ち主", code="forbidden")
            sets["shared"] = 1 if b["shared"] else 0
        if "owner_person" in b:
            o = b["owner_person"]
            if o is not None and (o not in acc.all_persons or not (acc.is_mine(o) or p.role == "admin")):
                raise HttpError(400, "持ち主にできない人", code="bad_person")
            sets["owner_person"] = o
    if "label" in b:
        label = clean_text(b.get("label"), 40)
        if not label:
            raise HttpError(400, "名前が要る", code="bad_label")
        sets["label"] = label
    if not sets:
        return {"ok": True}
    with _app().db.tx() as c:
        c.execute(f"UPDATE book_accounts SET {', '.join(f'{k}=?' for k in sets)} WHERE household_id=? AND account=?", (*sets.values(), hid, row["account"]))
    _audit(req, "book_account_updated:" + ",".join(sorted(sets)), row["account"])
    return {"ok": True}


@router.route("POST", "/api/book/accounts/{name}/reconcile")
def reconcile(req: Request) -> Any:
    """残高を調整：今の残高との差額を使途不明金として記録し、残高の確認を足す。"""
    _human_only(req)
    hid = _hh(req)
    acc = _access(req)
    p = req.principal
    assert p is not None
    _ensure_defaults(hid, p.actor)
    accts = _accounts(hid)
    row = accts.get(req.params["name"])
    if not _is_money(row) or not _can_write_account(req, acc, row):
        raise HttpError(404, "口座がない", code="not_found")
    assert row is not None
    b = req.json()
    actual, day = b.get("balance"), b.get("date") or _today()
    if not isinstance(actual, int) or isinstance(actual, bool) or not valid_date(day):
        raise HttpError(400, "今の残高は整数の円", code="bad_balance")
    st = _book(hid).state()
    calc = sum(q["amount"] for t in st.txns.values() if t["date"] <= day for q in t["postings"] if q["account"] == row["account"])
    diff = actual - calc
    events: list[dict[str, Any]] = []
    if diff:
        events.append({"op": "add", "txn": {"id": new_tx_id(f"{hid}|adjust|{row['account']}|{day}|{secrets.token_hex(4)}"), "date": day,
                                             "payee": "残高を調整", "narration": "",
                                             "postings": [{"account": row["account"], "amount": diff}, {"account": UNKNOWN, "amount": -diff}]}})
    events.append({"op": "balance", "account": row["account"], "date": day, "amount": actual})
    try:
        _book(hid).append(events, by=p.actor)
    except BookError as e:
        raise _book_error(e) from e
    _audit(req, "book_reconciled", row["account"])
    return {"ok": True, "difference": diff}


@router.route("GET", "/api/book/rules")
def list_rules(req: Request) -> Any:
    _human_only(req)
    hid = _hh(req)
    return {"rules": [{"id": r["id"], "pattern": r["pattern"], "category": r["category"]} for r in _rules(hid)]}


@router.route("POST", "/api/book/rules")
def add_rule(req: Request) -> Any:
    _human_only(req)
    hid = _hh(req)
    acc = _access(req)
    p = req.principal
    assert p is not None
    b = req.json()
    accts = _accounts(hid)
    target = b.get("category")
    row = accts.get(target) if isinstance(target, str) else None
    if row is None or (_is_money(row) and not _can_write_account(req, acc, row)):
        raise HttpError(400, "カテゴリか振替先を選ぶ", code="bad_category")
    if not clean_text(b.get("pattern"), 60):
        raise HttpError(400, "お店の文字が要る", code="bad_pattern")
    _add_rule(hid, b["pattern"], str(target), p.actor)
    return {"ok": True}


@router.route("POST", "/api/book/rules/{rid}/retire")
def retire_rule(req: Request) -> Any:
    _human_only(req)
    hid = _hh(req)
    with _app().db.tx() as c:
        n = c.execute("UPDATE book_rules SET retired_at=? WHERE id=? AND household_id=? AND retired_at IS NULL", (dbm.now_iso(), req.params["rid"], hid)).rowcount
    if not n:
        raise HttpError(404, "分類ルールがない", code="not_found")
    return {"ok": True}


# ---------------------------------------------------------------------------- 入出金
def _visible_txns(req: Request, hid: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    acc = _access(req)
    accts = _accounts(hid)
    st = _book(hid).state()
    return [t for t in st.txns.values() if _txn_visible(acc, t, accts)], accts


def _owner_filter(views: list[dict[str, Any]], owner: str | None) -> list[dict[str, Any]]:
    if not owner:
        return views
    if owner == "shared":
        return [v for v in views if not v["owner_person"]]
    return [v for v in views if v["owner_person"] == owner]


@router.route("GET", "/api/book/transactions")
def list_transactions(req: Request) -> Any:
    _human_only(req)
    hid = _hh(req)
    month = req.arg("month") or ""
    if month and not _MONTH.match(month):
        raise HttpError(400, "month は YYYY-MM", code="bad_month")
    txns, accts = _visible_txns(req, hid)
    if month:
        lo, hi = _month_range(month)
        txns = [t for t in txns if lo <= t["date"] < hi]
    links = _links(hid)
    views = _owner_filter([_txn_view(t, accts, links) for t in txns], req.arg("owner"))
    account, category, q = req.arg("account"), req.arg("category"), (req.arg("q") or "").strip()
    if account:
        views = [v for v in views if v["account"] == account or v["transfer_to"] == account]
    if category == "uncategorized":
        views = [v for v in views if v["category"] in UNCATEGORIZED.values()]
    elif category:
        def _in(c: Any) -> bool:
            return isinstance(c, str) and (c == category or c.startswith(category + ":"))
        views = [v for v in views if _in(v["category"]) or any(_in(x["category"]) for x in (v["parts"] or []))]
    if q:
        views = [v for v in views if q in v["payee"] or q in v["memo"]]
    views.sort(key=lambda v: (v["date"], v["id"]), reverse=True)
    return {"transactions": views[:1000], "truncated": len(views) > 1000}


@router.route("POST", "/api/book/transactions")
def add_transaction(req: Request) -> Any:
    """入力：口座・カテゴリ（または振替先の口座）・金額（口座から見た向き：支出は負、収入は正）。"""
    _human_only(req)
    hid = _hh(req)
    acc = _access(req)
    p = req.principal
    assert p is not None
    _ensure_defaults(hid, p.actor)
    b = req.json()
    accts = _accounts(hid)
    account, amount = b.get("account"), b.get("amount")
    row = accts.get(account) if isinstance(account, str) else None
    if not _is_money(row) or not _can_write_account(req, acc, row):
        raise HttpError(400, "口座を選ぶ", code="bad_account")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount == 0:
        raise HttpError(400, "金額は 0 でない整数の円", code="bad_amount")
    if b.get("parts"):
        postings = _split_postings({"account": account, "amount": amount}, b["parts"], accts)  # 分割
        target = postings[1]["account"]
    else:
        target = _check_target(req, acc, accts, b.get("category") or b.get("transfer_to"), account)
        postings = [{"account": account, "amount": amount}, {"account": target, "amount": -amount}]
    t: dict[str, Any] = {"id": new_tx_id(f"{hid}|manual|{secrets.token_hex(8)}"), "date": b.get("date") or _today(), "payee": b.get("payee"),
                         "memo": b.get("memo"), "postings": postings}
    if b.get("excluded") is True:
        t["excluded"] = True
    try:
        _book(hid).append([{"op": "add", "txn": t}], by=p.actor)
    except BookError as e:
        raise _book_error(e) from e
    if b.get("remember") and clean_text(b.get("payee"), 60):
        _add_rule(hid, b["payee"], target, p.actor)
    _audit(req, "book_txn_added", t["id"])
    return {"ok": True, "id": t["id"]}


def _txn_for_edit(req: Request, hid: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]], Access]:
    acc = _access(req)
    accts = _accounts(hid)
    t = _book(hid).state().txns.get(req.params["tid"])
    if t is None or not _txn_visible(acc, t, accts):
        raise HttpError(404, "入出金がない", code="not_found")
    if not all(_can_write_account(req, acc, accts.get(a)) for a in _money_accounts(t, accts)):
        raise HttpError(403, "この入出金は直せない", code="forbidden")
    return t, accts, acc


@router.route("POST", "/api/book/transactions/{tid}/update")
def update_transaction(req: Request) -> Any:
    """カテゴリ（2行の取引だけ）・お店・メモ・計算対象を直す。台帳には「直した」を追記する（上書きしない）。"""
    _human_only(req)
    hid = _hh(req)
    p = req.principal
    assert p is not None
    t, accts, acc = _txn_for_edit(req, hid)
    b = req.json()
    nt = json.loads(json.dumps(t))
    remember: tuple[str, str] | None = None
    if "category" in b:
        if len(t["postings"]) != 2:
            raise HttpError(400, "分割した入出金はここでは直せない", code="split")
        money = _money_accounts(t, accts)
        main = next(x for x in t["postings"] if x["account"] == money[0])
        target = _check_target(req, acc, accts, b.get("category"), main["account"])
        nt["postings"] = [main, {"account": target, "amount": -main["amount"]}]
        if b.get("remember") and t.get("payee"):
            remember = (t["payee"], target)
    if "payee" in b:
        nt["payee"] = clean_text(b.get("payee"), 120)
    if "memo" in b:
        nt["memo"] = clean_text(b.get("memo"), 500)
        nt.pop("narration", None)
    if "excluded" in b:
        if b["excluded"]:
            nt["excluded"] = True
        else:
            nt.pop("excluded", None)
    if nt != t:
        try:
            _book(hid).append([{"op": "correct", "txn": nt, "reason": "画面で直した"}], by=p.actor)
        except BookError as e:
            raise _book_error(e) from e
        _audit(req, "book_txn_updated", t["id"])
    if remember:
        _add_rule(hid, remember[0], remember[1], p.actor)
    return {"ok": True}


@router.route("POST", "/api/book/transactions/{tid}/delete")
def delete_transaction(req: Request) -> Any:
    _human_only(req)
    hid = _hh(req)
    p = req.principal
    assert p is not None
    t, _, _ = _txn_for_edit(req, hid)
    reason = clean_text(req.json().get("reason"), 200)
    if not reason:
        raise HttpError(400, "取り消す理由が要る", code="reason_required")
    try:
        _book(hid).append([{"op": "delete", "id": t["id"], "reason": reason}], by=p.actor)
    except BookError as e:
        raise _book_error(e) from e
    _audit(req, "book_txn_deleted", t["id"])
    return {"ok": True}


# ---------------------------------------------------------------------------- 家計簿（月の収支）
@router.route("GET", "/api/book/summary")
def summary(req: Request) -> Any:
    _human_only(req)
    hid = _hh(req)
    p = req.principal
    assert p is not None
    _ensure_defaults(hid, p.actor)
    month = req.arg("month") or _today()[:7]
    if not _MONTH.match(month):
        raise HttpError(400, "month は YYYY-MM", code="bad_month")
    txns, accts = _visible_txns(req, hid)
    lo, hi = _month_range(month)
    in_month = [t for t in txns if lo <= t["date"] < hi]
    views = {v["id"]: v for v in _owner_filter([_txn_view(t, accts) for t in in_month], req.arg("owner"))}
    tops: dict[str, dict[str, Any]] = {}
    income = expense = 0
    for t in in_month:
        if t["id"] not in views or t.get("excluded"):
            continue
        for q in t["postings"]:
            row = accts.get(q["account"])
            if row is None or row["kind"] not in CATEGORY_KINDS:
                continue
            val = q["amount"] if row["kind"] == "expense" else -q["amount"]  # 画面ではどちらも正の数
            if row["kind"] == "expense":
                expense += val
            else:
                income += val
            top = row.get("parent") or row["account"]
            trow = accts.get(top) or row
            g = tops.setdefault(top, {"category": top, "label": trow["label"], "kind": trow["kind"], "icon": trow.get("icon"), "amount": 0, "children": {}})
            g["amount"] += val
            if row.get("parent"):
                ch = g["children"].setdefault(row["account"], {"category": row["account"], "label": row["label"], "amount": 0})
                ch["amount"] += val
    groups = []
    for g in tops.values():
        g["children"] = sorted(g["children"].values(), key=lambda c: -c["amount"])
        groups.append(g)
    groups.sort(key=lambda g: (g["kind"], -g["amount"]))
    uncategorized = sum(1 for v in views.values() if v["category"] in UNCATEGORIZED.values())
    excluded = sum(1 for v in views.values() if v["excluded"])
    return {"month": month, "income": income, "expense": expense, "net": income - expense, "categories": groups,
            "uncategorized": uncategorized, "excluded": excluded, "count": len(views)}


@router.route("GET", "/api/book/status")
def book_status(req: Request) -> Any:
    """ホーム・ナビの件数（登録待ち）。"""
    _human_only(req)
    hid = _hh(req)
    acc = _access(req)
    accts = _accounts(hid)
    n = 0
    for r in _app().db.all("SELECT * FROM book_imports WHERE household_id=? AND status='pending'", (hid,)):
        row = dict(r)
        if _visible_account(acc, _batch_account(row, accts)):
            n += sum(1 for x in json.loads(row["items"]) if x.get("state", "pending") == "pending")
    return {"pending": n}

# ---------------------------------------------------------------------------- 申告に使う（家計簿 → 事実台帳の記録）
def _links(hid: str) -> dict[str, str]:
    return {r["txn_id"]: r["record_id"] for r in _app().db.all("SELECT txn_id, record_id FROM book_tax_links WHERE household_id=?", (hid,))}


@router.route("POST", "/api/book/transactions/{tid}/link")
def link_tax_record(req: Request) -> Any:
    """入出金から作った申告の記録（医療費の支払など）を結びつける。記録そのものは画面の人が /api/records で確定済み。"""
    _human_only(req)
    hid = _hh(req)
    p = req.principal
    assert p is not None
    t, _, _ = _txn_for_edit(req, hid)
    rid = req.json().get("record_id")
    head = _app().ledger(hid).heads("facts").get(rid) if isinstance(rid, str) else None
    if head is None or head["op"] == "delete":
        raise HttpError(404, "申告の記録がない", code="not_found")
    with _app().db.tx() as c:
        c.execute("INSERT OR IGNORE INTO book_tax_links(household_id, txn_id, record_id, created_by, created_at) VALUES (?,?,?,?,?)",
                  (hid, t["id"], rid, p.actor, dbm.now_iso()))
    _audit(req, "book_txn_linked", t["id"])
    return {"ok": True}


# ---------------------------------------------------------------------------- 分割・まとめて変更
def _split_postings(main: dict[str, Any], parts: Any, accts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """分割：口座の行はそのまま、カテゴリを複数の行に分ける。各行の金額は正の数で、合計は口座の金額（の絶対値）と同じ。"""
    if not isinstance(parts, list) or not 2 <= len(parts) <= 10:
        raise HttpError(400, "分割は2〜10行", code="bad_parts")
    out = [main]
    total = 0
    sign = -1 if main["amount"] > 0 else 1
    for x in parts:
        cat, amt = (x or {}).get("category"), (x or {}).get("amount")
        row = accts.get(cat) if isinstance(cat, str) else None
        if row is None or row["kind"] not in CATEGORY_KINDS or row.get("retired_at"):
            raise HttpError(400, "分割の行はカテゴリを選ぶ", code="bad_parts")
        if not isinstance(amt, int) or isinstance(amt, bool) or amt <= 0:
            raise HttpError(400, "分割の金額は正の整数の円", code="bad_parts")
        out.append({"account": cat, "amount": sign * amt})
        total += amt
    if total != abs(main["amount"]):
        raise HttpError(400, f"分割の合計（{total:,}円）が金額（{abs(main['amount']):,}円）と合わない", code="bad_parts")
    return out


@router.route("POST", "/api/book/transactions/{tid}/split")
def split_transaction(req: Request) -> Any:
    _human_only(req)
    hid = _hh(req)
    p = req.principal
    assert p is not None
    t, accts, _ = _txn_for_edit(req, hid)
    money = _money_accounts(t, accts)
    if len(money) != 1:
        raise HttpError(400, "振替は分割できない", code="split")
    main = next(x for x in t["postings"] if x["account"] == money[0])
    parts = req.json().get("parts")
    nt = json.loads(json.dumps(t))
    if isinstance(parts, list) and len(parts) == 1:
        # 分割をやめる（1行に戻す）
        cat = (parts[0] or {}).get("category")
        row = accts.get(cat) if isinstance(cat, str) else None
        if row is None or row["kind"] not in CATEGORY_KINDS:
            raise HttpError(400, "カテゴリを選ぶ", code="bad_category")
        nt["postings"] = [main, {"account": cat, "amount": -main["amount"]}]
    else:
        nt["postings"] = _split_postings(main, parts, accts)
    try:
        _book(hid).append([{"op": "correct", "txn": nt, "reason": "分割"}], by=p.actor)
    except BookError as e:
        raise _book_error(e) from e
    _audit(req, "book_txn_split", t["id"])
    return {"ok": True}


@router.route("POST", "/api/book/transactions/bulk")
def bulk_update(req: Request) -> Any:
    """まとめて変更：カテゴリ（2行の入出金だけ）か計算対象外。100件まで。"""
    _human_only(req)
    hid = _hh(req)
    acc = _access(req)
    p = req.principal
    assert p is not None
    b = req.json()
    ids = b.get("ids")
    if not isinstance(ids, list) or not 0 < len(ids) <= MAX_REGISTER:
        raise HttpError(400, f"ids は 1〜{MAX_REGISTER} 件", code="bad_items")
    accts = _accounts(hid)
    st = _book(hid).state()
    events = []
    skipped = 0
    for tid in ids:
        t = st.txns.get(tid) if isinstance(tid, str) else None
        if t is None or not _txn_visible(acc, t, accts) or not all(_can_write_account(req, acc, accts.get(a)) for a in _money_accounts(t, accts)):
            raise HttpError(404, "入出金がない（見えないか直せない）", code="not_found")
        nt = json.loads(json.dumps(t))
        if "category" in b:
            money = _money_accounts(t, accts)
            if len(t["postings"]) != 2 or len(money) != 1:
                skipped += 1  # 分割・振替はとばす
                continue
            main = next(x for x in t["postings"] if x["account"] == money[0])
            target = _check_target(req, acc, accts, b.get("category"), main["account"])
            nt["postings"] = [main, {"account": target, "amount": -main["amount"]}]
        if "excluded" in b:
            if b["excluded"]:
                nt["excluded"] = True
            else:
                nt.pop("excluded", None)
        if nt != t:
            events.append({"op": "correct", "txn": nt, "reason": "まとめて変更"})
    if events:
        try:
            _book(hid).append(events, by=p.actor)
        except BookError as e:
            raise _book_error(e) from e
    _audit(req, "book_txn_bulk", str(len(events)))
    return {"ok": True, "changed": len(events), "skipped": skipped}


# ---------------------------------------------------------------------------- 元に戻す（登録待ちの登録・対象外）
@router.route("POST", "/api/book/pending/undo")
def undo_pending(req: Request) -> Any:
    """登録したものは取り消して（台帳に「取消し：元に戻す」を追記）登録待ちに戻す。対象外にしたものは登録待ちに戻す。"""
    _human_only(req)
    hid = _hh(req)
    acc = _access(req)
    p = req.principal
    assert p is not None
    items = req.json().get("items")
    if not isinstance(items, list) or not 0 < len(items) <= MAX_REGISTER:
        raise HttpError(400, f"items は 1〜{MAX_REGISTER} 件", code="bad_items")
    accts = _accounts(hid)
    st = _book(hid).state()
    events: list[dict[str, Any]] = []
    updates: dict[str, list[dict[str, Any]]] = {}
    for w in items:
        bid, sid = (w or {}).get("batch"), (w or {}).get("source_id")
        r = _app().db.one("SELECT * FROM book_imports WHERE id=? AND household_id=?", (bid, hid))
        if r is None:
            raise HttpError(404, "取り込みがない", code="not_found")
        row = dict(r)
        if not _can_write_account(req, acc, _batch_account(row, accts)):
            raise HttpError(403, "この口座の明細は戻せない", code="forbidden")
        all_items = updates.get(bid) or json.loads(row["items"])
        it = next((x for x in all_items if x["source_id"] == sid), None)
        if it is None:
            raise HttpError(404, "その明細がない", code="not_found")
        if it.get("state") == "registered":
            tid = st.sources.get((row["source"], sid))
            if tid and not any(e["op"] == "delete" and e["id"] == tid for e in events):
                events.append({"op": "delete", "id": tid, "reason": "元に戻す"})
        it["state"] = "pending"
        it["decided_by"], it["decided_at"] = p.actor, dbm.now_iso()
        updates[bid] = all_items
    if events:
        try:
            _book(hid).append(events, by=p.actor)
        except BookError as e:
            raise _book_error(e) from e
    with _app().db.tx() as c:
        for bid, all_items in updates.items():
            c.execute("UPDATE book_imports SET items=?, status='pending', decided_by=NULL, decided_at=NULL WHERE id=?",
                      (json.dumps(all_items, ensure_ascii=False), bid))
    _audit(req, "book_pending_undo", ",".join(updates))
    return {"ok": True}


# ---------------------------------------------------------------------------- 予算・推移
def _month_totals(txns: list[dict[str, Any]], accts: dict[str, dict[str, Any]], lo: str, hi: str) -> tuple[int, int, dict[str, int]]:
    income = expense = 0
    tops: dict[str, int] = {}
    for t in txns:
        if not lo <= t["date"] < hi or t.get("excluded"):
            continue
        for q in t["postings"]:
            row = accts.get(q["account"])
            if row is None or row["kind"] not in CATEGORY_KINDS:
                continue
            if row["kind"] == "expense":
                expense += q["amount"]
                top = row.get("parent") or row["account"]
                tops[top] = tops.get(top, 0) + q["amount"]
            else:
                income -= q["amount"]
    return income, expense, tops


def _budgets(hid: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in _app().db.all("SELECT category, amount FROM book_budgets WHERE household_id=? ORDER BY seq", (hid,)):
        if r["amount"] is None:
            out.pop(r["category"], None)
        else:
            out[r["category"]] = r["amount"]
    return out


@router.route("GET", "/api/book/budget")
def get_budget(req: Request) -> Any:
    _human_only(req)
    hid = _hh(req)
    month = req.arg("month") or _today()[:7]
    if not _MONTH.match(month):
        raise HttpError(400, "month は YYYY-MM", code="bad_month")
    txns, accts = _visible_txns(req, hid)
    lo, hi = _month_range(month)
    _, expense, tops = _month_totals(txns, accts, lo, hi)
    budgets = _budgets(hid)
    rows = []
    for cat, amount in budgets.items():
        row = accts.get(cat)
        if row is None:
            continue
        spent = tops.get(cat, 0)
        rows.append({"category": cat, "label": row["label"], "icon": row.get("icon"), "budget": amount, "spent": spent, "remaining": amount - spent})
    rows.sort(key=lambda r: -r["budget"])
    total = sum(r["budget"] for r in rows)
    spent_in_budget = sum(r["spent"] for r in rows)
    today = _today()
    days_left = None
    if lo <= today < hi:
        last = _dt.date.fromisoformat(hi) - _dt.timedelta(days=1)
        days_left = (last - _dt.date.fromisoformat(today)).days + 1
    return {"month": month, "total": total, "spent": spent_in_budget, "remaining": total - spent_in_budget, "expense": expense,
            "days_left": days_left, "categories": rows}


@router.route("POST", "/api/book/budget")
def set_budget(req: Request) -> Any:
    """予算を設定する（大項目ごとの毎月の金額。null で外す）。前の値は消さずに追記する。"""
    _human_only(req)
    hid = _hh(req)
    p = req.principal
    assert p is not None
    items = req.json().get("items")
    if not isinstance(items, list) or len(items) > 50:
        raise HttpError(400, "items の形が違う", code="bad_items")
    accts = _accounts(hid)
    cur = _budgets(hid)
    rows = []
    for x in items:
        cat, amt = (x or {}).get("category"), (x or {}).get("amount")
        row = accts.get(cat) if isinstance(cat, str) else None
        if row is None or row["kind"] != "expense" or row.get("parent"):
            raise HttpError(400, "予算は支出の大項目に付ける", code="bad_category")
        if amt is not None and (not isinstance(amt, int) or isinstance(amt, bool) or amt <= 0 or amt > 10**10):
            raise HttpError(400, "予算は正の整数の円", code="bad_amount")
        if cur.get(cat) != amt:
            rows.append((hid, cat, amt, p.actor, dbm.now_iso()))
    if rows:
        with _app().db.tx() as c:
            c.executemany("INSERT INTO book_budgets(household_id, category, amount, created_by, created_at) VALUES (?,?,?,?,?)", rows)
        _audit(req, "book_budget_set", str(len(rows)))
    return {"ok": True}


@router.route("GET", "/api/book/trend")
def trend(req: Request) -> Any:
    """収支の推移（月ごとの収入・支出・収支）。"""
    _human_only(req)
    hid = _hh(req)
    try:
        n = max(3, min(24, int(req.arg("months") or "12")))
    except ValueError:
        n = 12
    end = req.arg("month") or _today()[:7]
    if not _MONTH.match(end):
        raise HttpError(400, "month は YYYY-MM", code="bad_month")
    txns, accts = _visible_txns(req, hid)
    owner = req.arg("owner")
    if owner:
        keep = {v["id"] for v in _owner_filter([_txn_view(t, accts) for t in txns], owner)}
        txns = [t for t in txns if t["id"] in keep]
    y, m = int(end[:4]), int(end[5:7])
    months = []
    for _ in range(n):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    out = []
    for mo in reversed(months):
        lo, hi = _month_range(mo)
        inc, exp, _ = _month_totals(txns, accts, lo, hi)
        out.append({"month": mo, "income": inc, "expense": exp, "net": inc - exp})
    return {"months": out}


# ---------------------------------------------------------------------------- 繰り返し
FREQS = ("daily", "weekly", "monthly", "monthend")


def occurrences(freq: str, start: str, until: str) -> list[str]:
    """繰り返しの日付（start から until まで）。毎月は start の日（ない月は月末）。"""
    s, u = _dt.date.fromisoformat(start), _dt.date.fromisoformat(until)
    out: list[str] = []
    if freq in ("daily", "weekly"):
        step = _dt.timedelta(days=1 if freq == "daily" else 7)
        d = s
        while d <= u and len(out) < 1000:
            out.append(d.isoformat())
            d += step
        return out
    y, m = s.year, s.month
    while len(out) < 1000:
        last = calendar.monthrange(y, m)[1]
        d = _dt.date(y, m, last if freq == "monthend" else min(s.day, last))
        if d > u:
            break
        if d >= s:
            out.append(d.isoformat())
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


@router.route("GET", "/api/book/recurring")
def list_recurring(req: Request) -> Any:
    _human_only(req)
    hid = _hh(req)
    acc = _access(req)
    accts = _accounts(hid)
    rows = _app().db.all("SELECT * FROM book_recurring WHERE household_id=? AND stopped_at IS NULL ORDER BY created_at", (hid,))
    return {"recurring": [{"id": r["id"], "account": r["account"], "category": r["category"], "amount": r["amount"], "payee": r["payee"],
                           "freq": r["freq"], "start_on": r["start_on"]} for r in rows if _visible_account(acc, accts.get(r["account"]))]}


@router.route("POST", "/api/book/recurring")
def add_recurring(req: Request) -> Any:
    _human_only(req)
    hid = _hh(req)
    acc = _access(req)
    p = req.principal
    assert p is not None
    b = req.json()
    accts = _accounts(hid)
    account, amount, freq, start = b.get("account"), b.get("amount"), b.get("freq"), b.get("start_on") or _today()
    row = accts.get(account) if isinstance(account, str) else None
    if not _is_money(row) or not _can_write_account(req, acc, row):
        raise HttpError(400, "口座を選ぶ", code="bad_account")
    target = _check_target(req, acc, accts, b.get("category") or b.get("transfer_to"), account)
    if not isinstance(amount, int) or isinstance(amount, bool) or amount == 0:
        raise HttpError(400, "金額は 0 でない整数の円", code="bad_amount")
    if freq not in FREQS:
        raise HttpError(400, "繰り返しは daily・weekly・monthly・monthend", code="bad_freq")
    if not valid_date(start):
        raise HttpError(400, "始める日は YYYY-MM-DD", code="bad_date")
    rid = dbm.new_id("rec", 6)
    with _app().db.tx() as c:
        c.execute("INSERT INTO book_recurring(id, household_id, account, category, amount, payee, memo, freq, start_on, created_by, created_at) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (rid, hid, account, target, amount, clean_text(b.get("payee"), 120), clean_text(b.get("memo"), 200), freq, start, p.actor, dbm.now_iso()))
    _audit(req, "book_recurring_added", rid)
    try:
        added = _run_recurring(req, hid)
    except BookError as e:
        raise _book_error(e) from e
    return {"ok": True, "id": rid, "added": added}


@router.route("POST", "/api/book/recurring/{rid}/stop")
def stop_recurring(req: Request) -> Any:
    _human_only(req)
    hid = _hh(req)
    acc = _access(req)
    accts = _accounts(hid)
    r = _app().db.one("SELECT * FROM book_recurring WHERE id=? AND household_id=? AND stopped_at IS NULL", (req.params["rid"], hid))
    if r is None or not _can_write_account(req, acc, accts.get(r["account"])):
        raise HttpError(404, "繰り返しがない", code="not_found")
    with _app().db.tx() as c:
        c.execute("UPDATE book_recurring SET stopped_at=? WHERE id=?", (dbm.now_iso(), r["id"]))
    _audit(req, "book_recurring_stopped", r["id"])
    return {"ok": True}


def _run_recurring(req: Request, hid: str) -> int:
    """期日が来た繰り返しを記録する（同じ日の分は二度入らない：取得元 recurring・ID は「規則:日付」）。
    人が決めた規則を、人が家計簿を開いたときに実行する（画面のセッションでだけ呼ぶ）。"""
    acc = _access(req)
    p = req.principal
    assert p is not None
    accts = _accounts(hid)
    st = _book(hid).state()
    today = _today()
    events: list[dict[str, Any]] = []
    for r in _app().db.all("SELECT * FROM book_recurring WHERE household_id=? AND stopped_at IS NULL", (hid,)):
        if not _can_write_account(req, acc, accts.get(r["account"])) or r["category"] not in accts:
            continue
        for d in occurrences(r["freq"], r["start_on"], today):
            sid = f"{r['id']}:{d}"
            if ("recurring", sid) in st.sources or any(e["txn"]["source_id"] == sid for e in events):
                continue
            events.append({"op": "add", "txn": {
                "id": new_tx_id(f"{hid}|recurring|{sid}|{secrets.token_hex(4)}"), "date": d, "payee": r["payee"] or "", "narration": r["memo"] or "",
                "source": "recurring", "source_id": sid,
                "postings": [{"account": r["account"], "amount": r["amount"]}, {"account": r["category"], "amount": -r["amount"]}]}})
            if len(events) >= 400:
                break
    if events:
        _book(hid).append(events, by=p.actor)
        _audit(req, "book_recurring_run", str(len(events)))
    return len(events)


@router.route("POST", "/api/book/recurring/run")
def run_recurring(req: Request) -> Any:
    _human_only(req)
    hid = _hh(req)
    try:
        return {"ok": True, "added": _run_recurring(req, hid)}
    except BookError as e:
        raise _book_error(e) from e
