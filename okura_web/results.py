"""判定コアの結果（evaluate の JSON）を画面向けにまとめる。

約束（⑩ 結果は黙って丸めない）：
- 値は判定コアの値をそのまま出す（幅は幅のまま、未確定は未確定のまま）。ここで計算し直さない・丸めない。
- 未確定は、分かれ目（何で分かれているか：判断・選択・注入・事実・一次情報・公表待ち）と候補ごとの値を出し、決めるための質問にする。
- 対象外は理由の文を出す。年分の外は「まだ計算できない」。
- 根拠（法令・出典・使った記録の ID）と境目（あといくらで結論が変わるか）を出す。
- 様式の欄の値は、人が作成コーナーに写す前提で出す（送信・自動入力はしない）。
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

KEY_CONCEPTS: dict[str, list[str]] = {
    "所得税": [
        "所得税.給与等の収入金額",
        "所得税.給与所得の金額",
        "所得税.事業所得の金額",
        "所得税.雑所得の金額",
        "所得税.合計所得金額",
        "所得税.扶養親族に当たるか",
        "所得税.控除対象扶養親族に当たるか",
        "所得税.特定扶養親族に当たるか",
        "所得税.特定親族に当たるか",
        "所得税.勤労学生に当たるか",
        "所得税.扶養控除の額",
        "所得税.配偶者控除の額",
        "所得税.配偶者特別控除の額",
        "所得税.特定親族特別控除の額",
        "所得税.勤労学生控除の額",
        "所得税.基礎控除の額",
        "所得税.社会保険料控除の額",
        "所得税.医療費控除の額",
        "所得税.所得控除の合計",
        "所得税.課税総所得金額",
        "所得税.所得税及び復興特別所得税の額",
        "所得税.申告納税額",
        "所得税.還付される税額",
        "所得税.確定申告書の提出義務があるか",
    ],
    "住民税": [
        "住民税.合計所得金額",
        "住民税.所得割を課さない者か",
        "住民税.均等割を課さない者か",
        "住民税.所得控除の合計",
        "住民税.所得割の額",
        "住民税.均等割の額",
        "住民税.森林環境税の額",
    ],
    "国保": ["国保.軽減判定所得", "国保.軽減の区分", "国保.所得割額", "国保.保険料の額"],
    "国年": [
        "国年.保険料の月額",
        "国年.全額免除の所得基準を満たすか",
        "国年.一部免除の区分",
        "国年.学生納付特例の所得基準を満たすか",
        "国年.第3号被保険者に当たるか",
    ],
    "健保": ["健保.年間収入", "健保.収入の基準額", "健保.年間収入が収入の基準額未満か", "健保.被扶養者に当たるか"],
}

MEANS_ORDER = {"判断": 0, "事実": 1, "注入": 2, "一次情報": 3, "公表待ち": 4}
MEANS_HELP = {
    "判断": "人が決めること（判断・選択）。決めて記録すると結論が決まる",
    "事実": "事実の記録が足りない。記録を足すと決まる",
    "注入": "市町村・保険者ごとの値（注入データ）が要る。出典つきで入れると決まる",
    "一次情報": "法令などの一次情報で決まらない（端数・法令の読み）。入力では決まらない。値は幅で示す",
    "公表待ち": "政令などがまだ公表されていない。公表後に okura-gov のバージョンを上げると決まる",
}


def wareki(year: int) -> str:
    return f"令和{year - 2018}年" if year >= 2019 else f"{year}年"


def time_key(t: dict[str, Any]) -> str:
    if "tax_year" in t:
        return f"Y{t['tax_year']}"
    if "fiscal_year" in t:
        return f"FY{t['fiscal_year']}"
    if "on" in t:
        return f"D{t['on']}"
    return json.dumps(t, sort_keys=True)


def time_label(t: dict[str, Any]) -> str:
    if "tax_year" in t:
        return f"{wareki(t['tax_year'])}分（{t['tax_year']}年の所得）"
    if "fiscal_year" in t:
        return f"{wareki(t['fiscal_year'])}度（{t['fiscal_year']}年度）"
    if "on" in t:
        return f"判定日 {t['on']}"
    return str(t)


def format_value(v: dict[str, Any] | None) -> str | None:
    """値の表示の文。丸めない（幅は幅のまま）。"""
    if not v:
        return None
    t = v.get("type")
    if t == "yen":
        return f"{v['amount']:,}円"
    if t == "yen_range":
        return f"{v['min']:,}円〜{v['max']:,}円（幅）"
    if t == "bool":
        return "はい" if v.get("value") else "いいえ"
    if t == "integer":
        return str(v.get("value"))
    if t == "category":
        return str(v.get("value"))
    if t == "date":
        return str(v.get("on"))
    return json.dumps(v, ensure_ascii=False)


class LoadedResult:
    def __init__(self, raw: dict[str, Any]):
        self.raw = raw
        self.basis: list[dict[str, Any]] = raw.get("basis", [])
        self.scenarios = {s["id"]: s for s in raw.get("scenarios", [])}
        self.values: dict[str, dict[str, dict[str, Any]]] = {
            sid: {v["id"]: v for v in s.get("values", [])} for sid, s in self.scenarios.items()
        }

    def scenario(self, sid: str = "base") -> dict[str, Any]:
        return self.scenarios.get(sid) or next(iter(self.scenarios.values()))


class ResultStore:
    """結果のファイルの読み込み（大きいので少しだけ持つ）。"""

    def __init__(self, keep: int = 3):
        self._cache: OrderedDict[str, LoadedResult] = OrderedDict()
        self._lock = threading.Lock()
        self.keep = keep

    def load(self, path: Path) -> LoadedResult:
        key = str(path)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        lr = LoadedResult(json.loads(path.read_bytes().decode("utf-8")))
        with self._lock:
            self._cache[key] = lr
            while len(self._cache) > self.keep:
                self._cache.popitem(last=False)
        return lr


# ---------------------------------------------------------------------------- まとめ
def _brief(v: dict[str, Any]) -> dict[str, Any]:
    u = v.get("undetermined")
    o = v.get("out_of_scope")
    out = {
        "id": v["id"],
        "concept": v["concept"],
        "person": v.get("person"),
        "time": v.get("time"),
        "value": v.get("value"),
        "display": format_value(v.get("value")),
        "states": v.get("states", []),
        "filing_item": v.get("filing_item", False),
    }
    if u:
        vals = sorted({json.dumps(oc.get("value"), sort_keys=True) for oc in u.get("outcomes", [])})
        out["undetermined"] = {
            "split_ids": [s["id"] for s in u.get("splits", [])],
            "candidate_values": [json.loads(x) for x in vals][:12],
            "evaluated": bool(u.get("outcomes")),
        }
    if o:
        out["out_of_scope"] = {"category": o.get("category"), "reason": o.get("reason")}
    return out


def _outcome_value_display(x: Any, vtype: str | None = None) -> str:
    if isinstance(x, dict):
        return format_value(x) or json.dumps(x, ensure_ascii=False)
    if isinstance(x, bool):
        return "はい" if x else "いいえ"
    if isinstance(x, int):
        return f"{x:,}円" if vtype in ("yen", "yen_range") else f"{x:,}"
    return str(x)


def _concept_types(values: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for v in values:
        val = v.get("value")
        if val and v["concept"] not in out:
            out[v["concept"]] = val.get("type")
    return out


def digest(lr: LoadedResult, *, okura_gov: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = lr.raw
    s = lr.scenario("base")
    values = s.get("values", [])
    persons = sorted({v["person"] for v in values if v.get("person")})
    times: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for v in values:
        k = time_key(v["time"])
        if k not in times:
            times[k] = {"key": k, "time": v["time"], "label": time_label(v["time"]), "institutions": set()}
        times[k]["institutions"].add(v["concept"].split(".")[0])
    time_list = []
    for k in sorted(times, key=lambda k: (k[0] != "Y", k)):
        t = times[k]
        t["institutions"] = sorted(t["institutions"])
        time_list.append(t)

    # 主な値
    key_order = [c for group in KEY_CONCEPTS.values() for c in group]
    key_set = set(key_order)
    key_values = [_brief(v) for v in values if v["concept"] in key_set]

    # 質問（分かれ目）
    ctypes = _concept_types(values)
    questions: dict[str, dict[str, Any]] = {}
    for v in values:
        u = v.get("undetermined")
        if not u:
            continue
        outcomes = u.get("outcomes", [])
        for sp in u.get("splits", []):
            q = questions.get(sp["id"])
            if q is None:
                target = dict(sp.get("target", {}))
                q = questions[sp["id"]] = {
                    "id": sp["id"],
                    "means": sp.get("means"),
                    "means_help": MEANS_HELP.get(sp.get("means", ""), ""),
                    "candidates": sp.get("candidates", []),
                    "splits_conclusion": sp.get("splits_conclusion", True),
                    "target": target,
                    "kind": target.get("kind"),
                    "persons": sorted({x for k, x in target.items() if isinstance(x, str) and x in persons}),
                    "not_evaluated_reason": target.get("評価しなかった理由"),
                    "affects": [],
                    "affects_count": 0,
                }
            q["affects_count"] += 1
            t = v.get("time") or {}
            yr = t.get("tax_year") or (int(str(t["on"])[:4]) if t.get("on") else None) or ((t["fiscal_year"] - 1) if t.get("fiscal_year") else None)
            if yr and yr not in q.setdefault("years", []):
                q["years"].append(yr)
                q["years"].sort()
            is_key = v["concept"] in key_set
            if len(q["affects"]) < 40 or is_key:
                per_cand: dict[str, list[str]] = {}
                for oc in outcomes:
                    cond = oc.get("conditions", {})
                    if sp["id"] in cond:
                        disp = _outcome_value_display(oc.get("value"), ctypes.get(v["concept"]))
                        lst = per_cand.setdefault(str(cond[sp["id"]]), [])
                        if disp not in lst:
                            lst.append(disp)
                q["affects"].append(
                    {
                        "value_id": v["id"],
                        "concept": v["concept"],
                        "person": v.get("person"),
                        "time": v.get("time"),
                        "key": is_key,
                        "per_candidate": per_cand,
                    }
                )
    qlist = list(questions.values())
    for q in qlist:
        q["affects"].sort(key=lambda a: (not a["key"], a["concept"]))
        q["affects"] = q["affects"][:40]
    qlist.sort(key=lambda q: (MEANS_ORDER.get(q["means"], 9), not q["splits_conclusion"], -q["affects_count"], q["id"]))

    # 対象外（理由ごと）
    oos: dict[tuple[str, str], dict[str, Any]] = {}
    for v in values:
        o = v.get("out_of_scope")
        if not o:
            continue
        key = (o.get("category") or "", o.get("reason") or "")
        g = oos.setdefault(
            key, {"category": key[0], "reason": key[1], "record_ids": sorted(set(o.get("record_ids") or [])), "values": []}
        )
        if len(g["values"]) < 30:
            g["values"].append({"value_id": v["id"], "concept": v["concept"], "person": v.get("person"), "time": v.get("time")})
        g["count"] = g.get("count", 0) + 1
    oos_items = sorted(oos.values(), key=lambda g: (-g["count"], g["reason"]))
    query_oos = []
    for item in s.get("out_of_scope", []):
        item = dict(item)
        if item.get("category") == "年分外":
            item["display"] = "まだ計算できない（okura-gov の対象の年分・年度・判定日の外）"
        query_oos.append(item)

    # 境目
    bounds = []
    for b in s.get("boundaries", []):
        bounds.append(
            {
                "id": b["id"],
                "concept": b["concept"],
                "person": b.get("person"),
                "time": b.get("time"),
                "compared": b.get("compared"),
                "criterion": {**b.get("criterion", {}), "basis": None},
                "criterion_basis": lr.basis[b["criterion"]["basis"]] if isinstance(b.get("criterion", {}).get("basis"), int) else None,
                "crossing_value": b.get("crossing_value"),
                "difference": b.get("difference"),
                "kind": b.get("kind"),
                "judgment": b.get("judgment"),
                "states": b.get("states", []),
            }
        )
    age_bounds = [
        {k: b.get(k) for k in ("id", "concept", "person", "time", "age", "criterion", "holds", "kind", "crossing_age", "boundary_on", "days_to_boundary", "states", "related")}
        for b in s.get("age_boundaries", [])
    ]

    # 様式
    forms = []
    for f in s.get("forms", []):
        forms.append(_form_summary(f))

    filing = s.get("filing", {})
    return {
        "ok": raw.get("ok"),
        "versions": {**raw.get("versions", {}), "okura_gov": okura_gov},
        "query": raw.get("query"),
        "injected": raw.get("injected"),
        "persons": persons,
        "times": time_list,
        "key_concepts": KEY_CONCEPTS,
        "key_values": key_values,
        "questions": qlist,
        "out_of_scope": oos_items,
        "query_out_of_scope": query_oos,
        "boundaries": bounds,
        "age_boundaries": age_bounds,
        "forms": forms,
        "filing": {
            "entries": len(filing.get("entries", [])),
            "withheld": [
                {k: w.get(k) for k in ("person", "time", "reasons", "concept", "value_id")} for w in filing.get("withheld", [])[:300]
            ],
        },
        "scenarios": [{"id": sid, "label": sc.get("label"), "differences": len(sc.get("differences", []))} for sid, sc in lr.scenarios.items()],
        "counts": {
            "values": len(values),
            "undetermined": sum(1 for v in values if v.get("undetermined")),
            "out_of_scope": sum(1 for v in values if v.get("out_of_scope")),
        },
    }


def _form_summary(f: dict[str, Any]) -> dict[str, Any]:
    """申告者 × 年分の様式の要約（欄の値そのものは forms_detail で）。"""
    out = {k: f.get(k) for k in ("person", "tax_year", "ok", "reason", "category", "means", "references", "blocking_value_ids")}
    forms = f.get("forms") or []
    out["forms"] = []
    for x in forms:
        st: dict[str, int] = {}
        for fld in x.get("fields", []):
            st[fld.get("status", "")] = st.get(fld.get("status", ""), 0) + 1
        out["forms"].append(
            {"form": x.get("form"), "name": x.get("name"), "use": x.get("use"), "use_reason": x.get("use_reason"), "fields": len(x.get("fields", [])), "status_counts": st}
        )
    out["filing_type"] = f.get("filing_type")
    out["not_produced"] = f.get("not_produced")
    return out


def forms_detail(lr: LoadedResult, person: str, tax_year: int, sid: str = "base") -> dict[str, Any] | None:
    s = lr.scenario(sid)
    for f in s.get("forms", []):
        fp = f.get("person") or f.get("filer")
        fy = f.get("tax_year")
        if fp == person and fy == tax_year:
            out = json.loads(json.dumps(f))
            for form in out.get("forms", []) or []:
                for fld in form.get("fields", []):
                    b = fld.get("basis")
                    if isinstance(b, int) and 0 <= b < len(lr.basis):
                        fld["basis_entry"] = lr.basis[b]
            return out
    return None


def value_detail(lr: LoadedResult, value_id: str, sid: str = "base") -> dict[str, Any] | None:
    v = lr.values.get(sid, {}).get(value_id)
    if v is None:
        return None
    out = dict(v)
    out["display"] = format_value(v.get("value"))
    out["basis_entries"] = [lr.basis[i] for i in v.get("basis", []) if isinstance(i, int) and 0 <= i < len(lr.basis)]
    deps = []
    for d in v.get("depends_on", [])[:200]:
        dv = lr.values.get(sid, {}).get(d)
        deps.append(
            {"value_id": d, "concept": dv["concept"] if dv else None, "person": dv.get("person") if dv else None,
             "display": format_value(dv.get("value")) if dv else None, "states": dv.get("states", []) if dv else []}
        )
    out["depends"] = deps
    u = v.get("undetermined")
    if u:
        vt = _concept_types(lr.scenario(sid).get("values", [])).get(v["concept"])
        out["outcomes_display"] = [
            {"conditions": oc.get("conditions", {}), "display": _outcome_value_display(oc.get("value"), vt)} for oc in u.get("outcomes", [])[:128]
        ]
    s = lr.scenario(sid)
    out["boundaries"] = [b for b in s.get("boundaries", []) if (b.get("judgment") or {}).get("value_id") == value_id or (b.get("compared") or {}).get("value_id") == value_id]
    return out


def values_for(lr: LoadedResult, *, person: str | None, tkey: str | None, institution: str | None, sid: str = "base") -> list[dict[str, Any]]:
    out = []
    for v in lr.scenario(sid).get("values", []):
        if person and v.get("person") != person:
            continue
        if tkey and time_key(v["time"]) != tkey:
            continue
        if institution and not v["concept"].startswith(institution + "."):
            continue
        out.append(_brief(v))
    return out


# ---------------------------------------------------------------------------- 質問 → 判断の下書き
def answer_template(q: dict[str, Any], meta: dict[str, Any], candidate: str | None) -> dict[str, Any] | None:
    """未確定の分かれ目（判断・選択）から、判断台帳に書く記録の下書きを作る（人が確かめて確定する）。"""
    kind = q.get("kind")
    if not kind:
        return None
    lk = next((k for k in meta.get("ledger", []) if k["kind"] == kind), None)
    if lk is None:
        return None
    target = q.get("target", {})
    subject = {name: target[name] for name in lk["subject"] if name in target}
    year = None
    if "tax_year" in target:
        year = int(target["tax_year"])
    elif "on" in target:
        year = int(str(target["on"])[:4])
    years = sorted(set(q.get("years") or ([year] if year else [])))
    when: dict[str, Any] | None = None
    w = lk["when"]
    if w == "period" and years:
        # 同じ分かれ目が効く年の全部を既定の期間にする（人が画面で直せる）
        when = {"from_on": f"{years[0]}-01-01", "to_on": f"{years[-1]}-12-31"}
    elif w == "tax_year" and year:
        when = {"tax_year": year}
    elif w == "fiscal_year":
        fy = target.get("fiscal_year") or (year + 1 if year else None)
        when = {"fiscal_year": fy} if fy else None
    elif w == "on" and target.get("on"):
        when = {"on": target["on"]}
    elif w == "on_or_period" and target.get("on"):
        when = {"on": target["on"]}
    value: Any = None
    if candidate is not None:
        schema = lk["value"]
        if isinstance(schema, dict) and schema.get("type") == "boolean":
            value = candidate == "true"
        elif isinstance(schema, dict) and schema.get("type") == "string":
            value = candidate
        elif kind == "選択.扶養の所属":
            value = {"filer": candidate, "document_type": "final_return", "section": "dependent_relative"}
        else:
            value = candidate
    rec: dict[str, Any] = {"kind": kind, "subject": subject, "value": value}
    if when is not None:
        rec["when"] = when
    if lk.get("mark"):
        rec["mark"] = lk["mark"]
    return {"section": lk["section"], "record": rec, "when_shape": w, "value_schema": lk["value"], "title": lk["title"]}
