"""エージェントの道具（MCP・外部 API・アプリ内のエージェントで共通）。

⑬ 人が決めることを AI に決めさせない：
- 道具は「読む」「計算する」「説明する」と「提案する」に分ける。確定（台帳への書き込み）の道具はない。
- 提案は確認待ち（proposals）に入り、画面で人が「確定」を押したときだけ台帳に書く。
- 判断・選択の提案には、候補と候補ごとの結果（最新の計算の未確定の分かれ目から）を付ける。

⑪ 外部に渡すとき（外部のエージェントのトークン、外部の LLM）：
- external_ai の同意のない人の記録・値は渡さない。
- 名前・住所・自由記述・ASCII でない文字列は伏せ字、生年月日は年だけ。原本（写真）は渡さない。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from . import api
from .access import Access, persons_in, redact_record
from .app import App
from .auth import Principal
from .engine import EngineError
from .results import answer_template, format_value, value_detail, forms_detail


class ToolError(Exception):
    pass


@dataclass
class ToolContext:
    app: App
    principal: Principal
    access: Access
    external: bool
    origin: str  # 提案の出どころ（mcp:<token>・api:<token>・inapp-agent）

    @property
    def hid(self) -> str:
        assert self.principal.household_id
        return self.principal.household_id

    def person_ok(self, pid: str | None) -> bool:
        if pid is None:
            return True
        if not self.access.sees_numbers(pid):
            return False
        return (not self.external) or self.access.external_ok(pid)

    def details_ok(self, persons: set[str]) -> bool:
        if not self.access.sees_details_of(persons):
            return False
        return (not self.external) or all(self.access.external_ok(p) for p in persons)

    def name(self, pid: str | None) -> str | None:
        if pid is None:
            return None
        if self.external:
            return self.access.pseudonyms().get(pid, pid)
        row = self.app.db.one("SELECT display_name FROM persons WHERE household_id=? AND person_id=?", (self.hid, pid))
        return row["display_name"] if row else pid


@dataclass
class Tool:
    name: str
    category: str  # read・compute・explain・propose
    description: str
    schema: dict[str, Any]
    fn: Callable[[ToolContext, dict[str, Any]], Any]


TOOLS: dict[str, Tool] = {}


def tool(name: str, category: str, description: str, props: dict[str, Any] | None = None, required: list[str] | None = None):
    def deco(fn):
        TOOLS[name] = Tool(
            name,
            category,
            description,
            {"type": "object", "properties": props or {}, "required": required or [], "additionalProperties": False},
            fn,
        )
        return fn

    return deco


def _latest(ctx: ToolContext):
    lr = ctx.app.latest_result(ctx.hid)
    if not lr:
        raise ToolError("まだ計算していない。run_calculation で計算する")
    return lr


# ---------------------------------------------------------------------------- 読む
@tool("household_overview", "read", "世帯の人（ID と表示名。外部では仮名）、同意の状態、確認待ちの件数、最新の計算の状態、okura-gov のバージョンを返す。最初に呼ぶ。")
def household_overview(ctx: ToolContext, args: dict[str, Any]) -> Any:
    persons = []
    for pid in ctx.access.all_persons:
        ok = ctx.person_ok(pid)
        persons.append({"person_id": pid, "name": ctx.name(pid) if ok else "非公開の人", "visible": ok, "is_me": pid == ctx.access.me})
    pending = ctx.app.db.one("SELECT COUNT(*) AS n FROM proposals WHERE household_id=? AND status='pending'", (ctx.hid,))["n"]
    lr = ctx.app.latest_result(ctx.hid)
    running = ctx.app.db.one("SELECT id, stage FROM jobs WHERE household_id=? AND status IN ('queued','running') LIMIT 1", (ctx.hid,))
    return {
        "persons": persons,
        "pending_proposals": pending,
        "latest_result": {"finished_at": lr["finished_at"], "hash": lr["result_hash"]} if lr else None,
        "running_job": dict(running) if running else None,
        "okura_gov": ctx.app.engine.okura_gov_version(),
        "external": ctx.external,
        "rules": "確定（データベースへの書き込み）はできない。判断・選択は候補と候補ごとの結果を示して提案する。人が画面で確定する。",
    }


@tool(
    "list_records",
    "read",
    "データベースの今の記録（事実・判断・選択）を返す。見える範囲（本人の同意）で絞る。外部では伏せ字。",
    {
        "kind": {"type": "string", "description": "記録の種類（例 salary_payment・medical_payment・判断.生計を一にする）"},
        "person": {"type": "string", "description": "人の ID（p-…）"},
        "section": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 500},
    },
)
def list_records(ctx: ToolContext, args: dict[str, Any]) -> Any:
    items, hidden = api.visible_records(ctx.hid, ctx.access, section=args.get("section"))
    out = []
    for it in items:
        rec = it["record"]
        if args.get("kind") and rec.get("kind") != args["kind"]:
            continue
        if args.get("person") and args["person"] not in it["persons"]:
            continue
        if not ctx.details_ok(set(it["persons"])):
            hidden += 1
            continue
        r = redact_record(rec) if ctx.external else rec
        out.append({"section": it["section"], "record": r, "has_original": bool(it["evidence"])})
    limit = int(args.get("limit") or 100)
    return {"records": out[:limit], "total": len(out), "hidden_count": hidden}


@tool("get_record", "read", "記録1件と、その訂正・取消しの履歴を返す。", {"record_id": {"type": "string"}}, ["record_id"])
def get_record(ctx: ToolContext, args: dict[str, Any]) -> Any:
    items, _ = api.visible_records(ctx.hid, ctx.access)
    for it in items:
        if it["record"]["id"] == args["record_id"]:
            if not ctx.details_ok(set(it["persons"])):
                break
            hist = ctx.app.ledger(ctx.hid).history(args["record_id"])
            if ctx.external:
                return {"record": redact_record(it["record"]), "history": [{"op": h["op"], "recorded_at": h["recorded_at"], "reason": "［伏せ字］" if h.get("reason") else None} for h in hist]}
            return {"record": it["record"], "history": hist, "evidence_ids": it["evidence"]}
    raise ToolError("その記録は見えないか、ない")


@tool(
    "vocabulary",
    "read",
    "記録・判断・選択の種類の一覧（kind を省略）か、1つの種類の欄のスキーマ（kind を指定）。提案を作るときに使う。",
    {"kind": {"type": "string"}},
)
def vocabulary(ctx: ToolContext, args: dict[str, Any]) -> Any:
    meta = ctx.app.meta()
    k = args.get("kind")
    if not k:
        return {
            "records": [{"kind": r["kind"], "section": r["section"], "title": r["title"], "when": r["when"]} for r in meta["records"]],
            "judgments_and_choices": [{"kind": r["kind"], "section": r["section"], "title": r["title"], "when": r["when"], "mark": r["mark"]} for r in meta["ledger"]],
        }
    for r in meta["records"] + meta["ledger"]:
        if r["kind"] == k:
            return r
    raise ToolError("その種類はない")


@tool("list_proposals", "read", "確認待ちの提案（人の確定を待っているもの）を返す。", {"status": {"type": "string", "enum": ["pending", "accepted", "rejected"]}})
def list_proposals_tool(ctx: ToolContext, args: dict[str, Any]) -> Any:
    rows = ctx.app.db.all(
        "SELECT * FROM proposals WHERE household_id=? AND status=? ORDER BY created_at DESC LIMIT 100", (ctx.hid, args.get("status", "pending"))
    )
    out = []
    for r in rows:
        payload = json.loads(r["payload"])
        ps = persons_in(payload.get("record") or {}, set(ctx.access.all_persons))
        if not ctx.details_ok(ps):
            continue
        rec = payload.get("record") or {}
        out.append({"id": r["id"], "kind": r["kind"], "status": r["status"], "origin": r["origin"], "created_at": r["created_at"], "record": redact_record(rec) if ctx.external else rec})
    return {"proposals": out}


# ---------------------------------------------------------------------------- 計算する
@tool(
    "run_calculation",
    "compute",
    "家族全体の計算をバックグラウンドで始める（数十秒）。ジョブの ID を返す。年分を省けば既定（所得税 2025・2026 年分、住民税など 2026・2027 年度）。範囲の外の年は『まだ計算できない』と返る。",
    {
        "income_tax_years": {"type": "array", "items": {"type": "integer"}},
        "fiscal_years": {"type": "array", "items": {"type": "integer"}},
        "judgment_dates": {"type": "array", "items": {"type": "string", "format": "date"}},
    },
)
def run_calculation(ctx: ToolContext, args: dict[str, Any]) -> Any:
    q = None
    if args:
        from .app import default_query

        q = default_query()
        if "income_tax_years" in args:
            q["income_tax_years"] = [int(x) for x in args["income_tax_years"]]
        if "fiscal_years" in args:
            fy = [int(x) for x in args["fiscal_years"]]
            q["resident_tax_fiscal_years"] = q["kokuho_fiscal_years"] = q["kokunen_fiscal_years"] = fy
        if "judgment_dates" in args:
            q["dependent_judgment_dates"] = [str(x) for x in args["judgment_dates"]]
    jid = ctx.app.enqueue(ctx.hid, ctx.principal.user_id, q)
    return {"job_id": jid, "note": "calculation_status で進み具合を見る"}


@tool("calculation_status", "compute", "計算のジョブの状態（順番待ち・計算中・完了・失敗）。", {"job_id": {"type": "string"}})
def calculation_status(ctx: ToolContext, args: dict[str, Any]) -> Any:
    if args.get("job_id"):
        row = ctx.app.db.one("SELECT id, status, stage, created_at, finished_at, error FROM jobs WHERE household_id=? AND id=?", (ctx.hid, args["job_id"]))
    else:
        row = ctx.app.db.one("SELECT id, status, stage, created_at, finished_at, error FROM jobs WHERE household_id=? ORDER BY created_at DESC LIMIT 1", (ctx.hid,))
    if row is None:
        raise ToolError("ジョブがない")
    d = dict(row)
    if d.get("error"):
        e = json.loads(d["error"])
        d["error"] = {"message": e.get("message"), "code": e.get("code")}
    return d


# ---------------------------------------------------------------------------- 説明する
def _digest(ctx: ToolContext) -> dict[str, Any]:
    lr = _latest(ctx)
    d = api.filter_digest(ctx.app.load_digest(ctx.hid, lr["result_hash"]), ctx.access)
    if ctx.external:
        vis = {p for p in d["persons"] if ctx.access.external_ok(p)}
        d = api.filter_digest(d, _OnlyPersons(ctx.access, vis))
    return d


class _OnlyPersons:
    """filter_digest に渡す、見える人を絞った窓口。"""

    def __init__(self, acc: Access, persons: set[str]):
        self._acc = acc
        self._persons = persons

    def sees_numbers(self, pid: str) -> bool:
        return pid in self._persons


@tool(
    "calculation_summary",
    "explain",
    "最新の計算の主な値（人 × 時点：所得・控除・税額・扶養・被扶養者の判定）。未確定・対象外はそのまま返す（丸めない）。",
    {"time": {"type": "string", "description": "時点のキー（Y2026・FY2027・D2026-12-31）。省略は全部"}},
)
def calculation_summary(ctx: ToolContext, args: dict[str, Any]) -> Any:
    d = _digest(ctx)
    t = args.get("time")
    rows = []
    from .results import time_key

    for v in d["key_values"]:
        if t and time_key(v["time"]) != t:
            continue
        rows.append(
            {
                "value_id": v["id"],
                "concept": v["concept"],
                "person": v["person"],
                "person_name": ctx.name(v["person"]),
                "time": v["time"],
                "display": v["display"],
                "states": v["states"],
                "undetermined": v.get("undetermined"),
                "out_of_scope": v.get("out_of_scope"),
            }
        )
    return {
        "versions": {"okura_gov": d["versions"].get("okura_gov"), "okura_core": d["versions"].get("okura_core")},
        "times": [{"key": x["key"], "label": x["label"]} for x in d["times"]],
        "values": rows,
        "hidden_persons": len(d.get("hidden_persons", [])),
        "questions": len(d["questions"]),
        "not_yet_computable": d.get("query_out_of_scope", []),
    }


@tool("explain_value", "explain", "値1つの根拠（法令・出典・使った記録の ID）、依存する値、未確定の候補ごとの値、境目を返す。", {"value_id": {"type": "string"}}, ["value_id"])
def explain_value(ctx: ToolContext, args: dict[str, Any]) -> Any:
    lr = _latest(ctx)
    v = value_detail(ctx.app.load_result(ctx.hid, lr["result_hash"]), args["value_id"])
    if v is None:
        raise ToolError("その値はない")
    if not ctx.person_ok(v.get("person")):
        raise ToolError("その人の値は見えない（本人の同意がない）")
    v["depends"] = [x for x in v["depends"] if x.get("person") is None or ctx.person_ok(x["person"])]
    keep = ("id", "concept", "person", "time", "display", "states", "basis_entries", "depends", "facts", "undetermined", "outcomes_display", "out_of_scope", "boundaries", "filing_item")
    return {k: v.get(k) for k in keep}


@tool(
    "list_questions",
    "explain",
    "未確定の分かれ目（何で結論が分かれているか）と候補ごとの値。means=判断 は人が決めること（提案の材料）、注入 は市町村・保険者の値、一次情報・公表待ちは入力では決まらない。",
    {"means": {"type": "string", "enum": ["判断", "事実", "注入", "一次情報", "公表待ち"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
)
def list_questions(ctx: ToolContext, args: dict[str, Any]) -> Any:
    d = _digest(ctx)
    qs = [q for q in d["questions"] if not args.get("means") or q["means"] == args["means"]]
    limit = int(args.get("limit") or 20)
    out = []
    for q in qs[:limit]:
        out.append({**{k: q[k] for k in ("id", "means", "means_help", "candidates", "kind", "persons", "not_evaluated_reason", "affects_count")}, "target": q["target"], "affects": q["affects"][:10]})
    return {"questions": out, "total": len(qs)}


@tool("list_out_of_scope", "explain", "対象外の値と理由の文（理由ごと）。年分の外は『まだ計算できない』。")
def list_out_of_scope(ctx: ToolContext, args: dict[str, Any]) -> Any:
    d = _digest(ctx)
    return {"by_reason": d["out_of_scope"][:50], "query": d.get("query_out_of_scope", [])}


@tool("list_boundaries", "explain", "境目（あといくらで結論が変わるか）と年齢の境目。", {"person": {"type": "string"}})
def list_boundaries(ctx: ToolContext, args: dict[str, Any]) -> Any:
    d = _digest(ctx)
    bs = [b for b in d["boundaries"] if not args.get("person") or b["person"] == args["person"]]
    out = []
    for b in bs:
        out.append({**b, "explain": f"{b['compared']['concept'] if b.get('compared') else ''} が {b.get('crossing_value')} を{'超える' if b.get('kind') == '上限' else '下回る'}と結論が変わる。今との差 {b.get('difference')}"})
    return {"boundaries": out, "age_boundaries": [b for b in d["age_boundaries"] if not args.get("person") or b["person"] == args["person"]]}


@tool(
    "form_fields",
    "explain",
    "申告書の様式の欄の値（人が確定申告書等作成コーナーに写すためのもの）。e-Tax への送信や作成コーナーへの自動入力はしない。",
    {"person": {"type": "string"}, "tax_year": {"type": "integer"}},
    ["person", "tax_year"],
)
def form_fields(ctx: ToolContext, args: dict[str, Any]) -> Any:
    if not ctx.person_ok(args["person"]):
        raise ToolError("その人の値は見えない")
    lr = _latest(ctx)
    f = forms_detail(ctx.app.load_result(ctx.hid, lr["result_hash"]), args["person"], int(args["tax_year"]))
    if f is None:
        raise ToolError("その人・年分の様式の値がない")
    if not f.get("ok"):
        return {"ok": False, "reason": f.get("reason"), "category": f.get("category")}
    forms = []
    for form in f.get("forms", []):
        fields = [
            {k: x.get(k) for k in ("code", "name", "position", "status", "value", "unit", "reason", "marks")}
            for x in form.get("fields", [])
            if x.get("status") in ("出力", "未確定", "値なし")
        ]
        if ctx.external:
            for x in fields:
                if isinstance(x.get("value"), str) and any(ord(c) > 127 for c in x["value"]):
                    x["value"] = "［伏せ字］"
        forms.append({"form": form.get("form"), "name": form.get("name"), "use": form.get("use"), "fields": fields})
    return {"ok": True, "forms": forms, "note": "人が作成コーナーに写す。送信・自動入力はしない"}


# ---------------------------------------------------------------------------- 提案する（確定は人）
def _require_propose(ctx: ToolContext) -> None:
    if ctx.principal.kind == "token" and "propose" not in ctx.principal.scopes:
        raise ToolError("このトークンには提案（propose）の権限がない")


_WHEN_KEYS = ("on", "from_on", "to_on", "tax_year", "fiscal_year")


def normalize_record(rec: dict[str, Any]) -> dict[str, Any]:
    """AI がよく間違える形を直す：日付を when の外に書いた・id などを書いた。"""
    rec = dict(rec)
    for k in ("id", "recorded_at", "source"):
        rec.pop(k, None)
    moved = {k: rec.pop(k) for k in _WHEN_KEYS if k in rec}
    if moved:
        w = dict(rec.get("when") or {})
        for k, v in moved.items():
            w.setdefault(k, v)
        rec["when"] = w
    return rec


def check_records(ctx: ToolContext, items: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """提案の前に、記録をデータベースの写しに入れて確かめる（本物は変えない）。問題の文の一覧を返す（空なら通った）。"""
    from .engine import EngineError as _EE
    from .server import HttpError as _HE

    try:
        drafts = []
        for section, rec in items:
            r = api._prepare_record(ctx.hid, ctx.access, section, json.loads(json.dumps(rec)), [])
            drafts.append({"op": "add", "section": section, "record": r})
        ctx.app.ledger(ctx.hid).write("facts", drafts, recorded_by_person=ctx.principal.person_id or "p-agent", dry_run=True)
    except _HE as e:
        return [str(e)]
    except _EE as e:
        probs = [f"{p.get('where', '')}: {p.get('message', '')}" for p in (e.problems or [])[:10]]
        return probs or [str(e)]
    return []


@tool(
    "propose_record",
    "propose",
    "事実の記録（給与・医療費・経費など）を提案する。確認待ちに入り、人が画面で確かめて確定するまでデータベースに書かない。record は vocabulary の欄に従う（id・recorded_at は書かない）。",
    {
        "section": {"type": "string", "enum": list(api.RECORD_SECTIONS)},
        "record": {"type": "object"},
        "rationale": {"type": "string", "description": "なぜこの記録か（読み取った書類・根拠）"},
        "evidence_id": {"type": "string"},
    },
    ["section", "record", "rationale"],
)
def propose_record(ctx: ToolContext, args: dict[str, Any]) -> Any:
    _require_propose(ctx)
    rec = normalize_record(args["record"])
    if not args.get("_checked"):
        probs = check_records(ctx, [(args["section"], rec)])
        if probs:
            raise ToolError("この記録はデータベースの形に合わない。直して提案し直す：" + " / ".join(probs))
    ps = persons_in(rec, set(ctx.access.all_persons))
    if ctx.external and not all(ctx.access.external_ok(p) for p in ps):
        raise ToolError("外部の AI の同意のない人の記録は提案できない")
    pid = api.create_proposal(ctx.hid, kind="record", payload={"section": args["section"], "record": rec}, rationale=args.get("rationale"), candidates=None, evidence_id=args.get("evidence_id"), origin=ctx.origin, created_by=ctx.origin)
    return {"proposal_id": pid, "status": "pending", "note": "人が画面の『確認待ち』で確定するまでデータベースには書かない"}


@tool(
    "propose_judgment",
    "propose",
    "判断・選択（生計を一にする、どちらの扶養に入れるか、還付申告をするか など）を提案する。question_id（list_questions の id）を渡すと、候補と候補ごとの結果が付く。決めるのは人。",
    {
        "question_id": {"type": "string"},
        "candidate": {"type": "string", "description": "提案する候補（question の candidates のどれか）"},
        "section": {"type": "string", "enum": ["judgments", "choices"]},
        "record": {"type": "object", "description": "question_id がないとき：kind・subject・when・value"},
        "rationale": {"type": "string"},
    },
    ["rationale"],
)
def propose_judgment(ctx: ToolContext, args: dict[str, Any]) -> Any:
    _require_propose(ctx)
    candidates = None
    if args.get("question_id"):
        d = _digest(ctx)
        q = next((x for x in d["questions"] if x["id"] == args["question_id"]), None)
        if q is None:
            raise ToolError("その分かれ目はない（見えないか、もう決まっている）")
        if q["means"] != "判断":
            raise ToolError("この分かれ目は人の判断で決まるものではない（注入・一次情報・公表待ち・事実）")
        meta = ctx.app.meta()
        cand = args.get("candidate")
        tmpl = answer_template(q, meta, cand)
        if tmpl is None:
            raise ToolError("この分かれ目の判断の下書きを作れない。record を渡す")
        section = tmpl["section"]
        rec = tmpl["record"]
        if args.get("record"):
            rec.update({k: v for k, v in args["record"].items() if k in ("subject", "when", "value", "basis")})
        candidates = {"question_id": q["id"], "candidates": q["candidates"], "per_candidate": [{"value_id": a["value_id"], "concept": a["concept"], "person": a["person"], "per_candidate": a["per_candidate"]} for a in q["affects"][:10]]}
    else:
        if not args.get("record") or not args.get("section"):
            raise ToolError("question_id か、section と record を渡す")
        section = args["section"]
        rec = dict(args["record"])
    for k in ("id", "judged_by", "judged_at", "chosen_by", "chosen_at", "recorded_at"):
        rec.pop(k, None)
    kind = "choice" if section == "choices" else "judgment"
    pid = api.create_proposal(ctx.hid, kind=kind, payload={"section": section, "record": rec}, rationale=args.get("rationale"), candidates=candidates, evidence_id=None, origin=ctx.origin, created_by=ctx.origin)
    return {"proposal_id": pid, "status": "pending", "note": "判断・選択は人が画面で決めて確定する。だれがいつ決めたかが記録される"}


@tool(
    "propose_forecast",
    "propose",
    "収入の見込み（見込み.年間収入。印『予測』）を提案する。被扶養者の判定の材料。予測の値からは申告用の値は出ない。",
    {
        "person": {"type": "string"},
        "on": {"type": "string", "format": "date", "description": "見込みを立てる日（判定日）"},
        "amounts": {"type": "array", "items": {"type": "object", "properties": {"income_type": {"type": "string"}, "amount": {"type": "integer"}}, "required": ["income_type", "amount"]}},
        "rationale": {"type": "string"},
    },
    ["person", "on", "amounts", "rationale"],
)
def propose_forecast(ctx: ToolContext, args: dict[str, Any]) -> Any:
    _require_propose(ctx)
    if not ctx.person_ok(args["person"]):
        raise ToolError("その人の値は見えない")
    rec = {
        "kind": "見込み.年間収入",
        "subject": {"person": args["person"]},
        "when": {"on": args["on"]},
        "value": {"amounts": [{"income_type": a["income_type"], "amount": int(a["amount"])} for a in args["amounts"]]},
        "mark": "予測",
    }
    pid = api.create_proposal(ctx.hid, kind="forecast", payload={"section": "judgments", "record": rec}, rationale=args.get("rationale"), candidates=None, evidence_id=None, origin=ctx.origin, created_by=ctx.origin)
    return {"proposal_id": pid, "status": "pending"}


# ---------------------------------------------------------------------------- 会話のカード（アプリ内の AI）
@tool(
    "propose_records",
    "propose",
    "記録をまとめて提案する（添付の表・PDF・写真から読んだ複数の記録）。1件ずつ確認待ちに入り、画面の『この内容で登録します』のカードで人が確かめて登録する。"
    "読めない値は推測で埋めない（欄を空にして rationale に書く）。evidence_id（添付の ID）を付けると原本と結びつく。",
    {
        "items": {"type": "array", "maxItems": 50, "items": {"type": "object", "properties": {
            "section": {"type": "string", "enum": list(api.RECORD_SECTIONS)},
            "record": {"type": "object"},
            "rationale": {"type": "string"},
            "evidence_id": {"type": "string"},
        }, "required": ["section", "record"]}},
    },
    ["items"],
)
def propose_records(ctx: ToolContext, args: dict[str, Any]) -> Any:
    _require_propose(ctx)
    items = args.get("items")
    if not isinstance(items, list) or not 0 < len(items) <= 50:
        raise ToolError("items は 1〜50 件")
    ids, errors = [], []
    good: list[tuple[int, dict[str, Any]]] = []
    for i, it in enumerate(items):
        if not isinstance(it, dict) or it.get("section") not in api.RECORD_SECTIONS or not isinstance(it.get("record"), dict):
            errors.append({"index": i, "error": "section と record が要る"})
            continue
        good.append((i, {**it, "record": normalize_record(it["record"])}))
    # まとめて確かめる。だめなら1件ずつ確かめて、だめな行を AI に返す
    whole_ok = not check_records(ctx, [(it["section"], it["record"]) for _, it in good]) if good else True
    for i, it in good:
        probs = [] if whole_ok else check_records(ctx, [(it["section"], it["record"])])
        if probs:
            errors.append({"index": i, "error": "データベースの形に合わない：" + " / ".join(probs)})
            continue
        try:
            r = propose_record(ctx, {"section": it["section"], "record": it["record"], "rationale": it.get("rationale") or "添付から読んだ",
                                     "evidence_id": it.get("evidence_id"), "_checked": True})
            ids.append(r["proposal_id"])
        except ToolError as e:
            errors.append({"index": i, "error": str(e)})
    return {"proposal_ids": ids, "errors": errors, "note": "画面のカードで人が確かめて登録するまでデータベースには書かない"}


@tool(
    "ask_user",
    "ui",
    "人に選択肢で質問する（画面にボタンが出る）。人が決めること（判断・選択）や、読み取りで迷った点を聞くときに使う。"
    "呼んだらそこで返事を止めて、人の答え（次のメッセージ）を待つ。選択肢は短く（2〜6個）。",
    {
        "question": {"type": "string"},
        "options": {"type": "array", "minItems": 2, "maxItems": 6, "items": {"type": "string"}},
    },
    ["question", "options"],
)
def ask_user(ctx: ToolContext, args: dict[str, Any]) -> Any:
    q = str(args.get("question") or "").strip()[:300]
    opts = [str(o).strip()[:60] for o in (args.get("options") or []) if str(o).strip()][:6]
    if not q or len(opts) < 2:
        raise ToolError("question と 2〜6 個の options が要る")
    return {"asked": True, "question": q, "options": opts, "note": "ここで止めて、人の答えを待つ"}


@tool(
    "propose_book_entries",
    "propose",
    "家計簿の入出金（通帳・カードの明細・レシートの表から読んだもの）を、家計簿の『登録待ち』に入れる。人が画面で登録する。"
    "amount は口座から見た向き（入金は正、出金・カードの利用は負）の整数の円。category は家計簿のカテゴリの勘定（例 Expenses:Food:Groceries。分からなければ省く）。"
    "同じ明細を二度入れないよう、id は明細ごとに決まる文字（日付と行の番号など）にする。",
    {
        "account_label": {"type": "string", "description": "口座の名前（例：〇〇銀行・〇〇カード・財布）"},
        "account_kind": {"type": "string", "enum": ["bank", "card", "emoney", "cash", "securities", "other"]},
        "entries": {"type": "array", "maxItems": 500, "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "date": {"type": "string"}, "amount": {"type": "integer"},
            "payee": {"type": "string"}, "memo": {"type": "string"}, "category": {"type": "string"},
        }, "required": ["id", "date", "amount"]}},
    },
    ["account_label", "account_kind", "entries"],
)
def propose_book_entries(ctx: ToolContext, args: dict[str, Any]) -> Any:
    _require_propose(ctx)
    import hashlib

    from . import api_book
    from .server import HttpError

    label = str(args.get("account_label") or "").strip()[:40]
    if not label:
        raise ToolError("account_label が要る")
    key = "chat-" + hashlib.sha256(label.encode("utf-8")).hexdigest()[:10]
    body = {"source": "chat", "account": {"key": key, "kind": args.get("account_kind") or "bank", "label": label}, "transactions": args.get("entries") or []}
    try:
        out = api_book.create_batch(ctx.hid, ctx.origin, ctx.principal.person_id, body)
    except HttpError as e:
        raise ToolError(str(e)) from e
    return {**out, "note": "家計簿の『登録待ち』に入れた。人が画面で登録する"}


# ---------------------------------------------------------------------------- 呼び出し
def specs(categories: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    return [
        {"name": t.name, "category": t.category, "description": t.description, "input_schema": t.schema}
        for t in TOOLS.values()
        if categories is None or t.category in categories
    ]


def call(ctx: ToolContext, name: str, args: dict[str, Any]) -> Any:
    t = TOOLS.get(name)
    if t is None:
        raise ToolError(f"知らない道具: {name}")
    if ctx.principal.kind == "token" and t.category != "propose" and "read" not in ctx.principal.scopes:
        raise ToolError("このトークンには読む（read）の権限がない")
    if not isinstance(args, dict):
        raise ToolError("引数はオブジェクト")
    try:
        return t.fn(ctx, args)
    except EngineError as e:
        raise ToolError(str(e)) from e
    except KeyError as e:
        raise ToolError(f"引数が足りない: {e}") from e


def context_for(app: App, principal: Principal, *, external: bool, origin: str) -> ToolContext:
    return ToolContext(app, principal, Access.load(app.db, principal), external, origin)


__all__ = ["TOOLS", "ToolContext", "ToolError", "call", "context_for", "specs", "format_value"]
