"""テストの共通の材料。架空の世帯だけを使う（人の ID は p-a・p-b・p-c、名前は 架空太郎 など）。"""

from __future__ import annotations

import copy
from typing import Any

from okura_web.access import Access
from okura_web.auth import Principal

HID = "hh-0000000000000000"


def consent(value: int = 1) -> dict[str, Any]:
    return {"value": value, "decided_by": "u-1", "decided_at": "2026-01-01T00:00:00+09:00", "note": None}


def make_access(
    me: str | None = "p-a",
    *,
    user_id: str = "u-1",
    consents: dict[tuple[str, str], dict[str, Any]] | None = None,
    account_persons: set[str] | None = None,
    managed: set[str] | None = None,
    all_persons: list[str] | None = None,
) -> Access:
    """架空の世帯：p-a（架空太郎・アカウントあり）、p-b（架空花子・アカウントあり）、p-c（架空一郎・子・アカウントなし、p-a が管理）。"""
    return Access(
        principal=Principal("session", user_id, "架空太郎", household_id=HID, person_id=me),
        consents=dict(consents or {}),
        account_persons=set({"p-a", "p-b"} if account_persons is None else account_persons),
        managed=set({"p-c"} if managed is None else managed),
        all_persons=list(["p-a", "p-b", "p-c"] if all_persons is None else all_persons),
    )


def yen(n: int) -> dict[str, Any]:
    return {"type": "yen", "amount": n}


def boolean(b: bool) -> dict[str, Any]:
    return {"type": "bool", "value": b}


Y2026 = {"tax_year": 2026}
FY2027 = {"fiscal_year": 2027}
D20261231 = {"on": "2026-12-31"}

SPLIT_LIVELIHOOD = {
    "id": "s-seikei-p-c",
    "means": "判断",
    "target": {"kind": "判断.生計を一にするか", "person": "p-c", "tax_year": 2026},
    "candidates": ["true", "false"],
    "splits_conclusion": True,
}
SPLIT_INJECT = {
    "id": "s-inj-kokuho",
    "means": "注入",
    "target": {"kind": "注入.国保の料率", "fiscal_year": 2027},
    "candidates": [],
    "splits_conclusion": True,
}


def _raw_result() -> dict[str, Any]:
    values = [
        {"id": "v-1", "concept": "所得税.合計所得金額", "person": "p-a", "time": Y2026, "value": yen(3_000_000), "states": []},
        {
            "id": "v-2",
            "concept": "所得税.扶養親族に当たるか",
            "person": "p-c",
            "time": Y2026,
            "value": None,
            "states": ["未確定"],
            "undetermined": {
                "splits": [SPLIT_LIVELIHOOD],
                "outcomes": [
                    {"conditions": {"s-seikei-p-c": "true"}, "value": boolean(True)},
                    {"conditions": {"s-seikei-p-c": "false"}, "value": boolean(False)},
                ],
            },
        },
        {
            "id": "v-3",
            "concept": "所得税.扶養控除の額",
            "person": "p-a",
            "time": Y2026,
            "value": None,
            "states": ["未確定"],
            "undetermined": {
                "splits": [SPLIT_LIVELIHOOD],
                "outcomes": [
                    {"conditions": {"s-seikei-p-c": "true"}, "value": yen(380_000)},
                    {"conditions": {"s-seikei-p-c": "false"}, "value": yen(0)},
                ],
            },
        },
        {
            "id": "v-4",
            "concept": "住民税.所得割の額",
            "person": "p-b",
            "time": FY2027,
            "value": {"type": "yen_range", "min": 100_000, "max": 100_999},
            "states": ["幅"],
        },
        {
            "id": "v-5",
            "concept": "所得税.内部の値",
            "person": "p-b",
            "time": Y2026,
            "value": None,
            "states": ["対象外"],
            "out_of_scope": {"category": "対象外", "reason": "架空の理由：この所得は対象外", "record_ids": ["f-9", "f-9", "f-8"]},
        },
        {
            "id": "v-6",
            "concept": "国保.保険料の額",
            "person": "p-b",
            "time": FY2027,
            "value": None,
            "states": ["未確定"],
            "undetermined": {"splits": [SPLIT_INJECT], "outcomes": []},
        },
        {"id": "v-7", "concept": "国年.全額免除の所得基準を満たすか", "person": "p-c", "time": D20261231, "value": boolean(False), "states": []},
    ]
    return {
        "ok": True,
        "versions": {"core": "0.0-test"},
        "query": {"income_tax_years": [2026]},
        "injected": [],
        "basis": [{"law": "架空法第1条"}, {"law": "架空法第2条"}],
        "scenarios": [
            {
                "id": "base",
                "label": "今の記録",
                "values": values,
                "out_of_scope": [{"category": "年分外", "reason": "2030年分は範囲の外"}],
                "boundaries": [
                    {
                        "id": "b-1",
                        "concept": "所得税.扶養親族に当たるか",
                        "person": "p-c",
                        "time": Y2026,
                        "compared": {"value_id": "v-x"},
                        "criterion": {"amount": 580_000, "basis": 1},
                        "crossing_value": 580_001,
                        "difference": 80_000,
                        "kind": "以下",
                        "judgment": {"value_id": "v-2"},
                        "states": [],
                    },
                    {"id": "b-2", "concept": "住民税.所得割の額", "person": "p-b", "time": FY2027, "criterion": {"amount": 1}},
                ],
                "age_boundaries": [
                    {"id": "a-1", "concept": "所得税.特定扶養親族に当たるか", "person": "p-c", "time": Y2026, "age": 19, "secret_extra": "x"},
                    {"id": "a-2", "concept": "国年.保険料の月額", "person": "p-b", "time": FY2027, "age": 40},
                ],
                "forms": [
                    {
                        "person": "p-a",
                        "tax_year": 2026,
                        "ok": True,
                        "forms": [
                            {
                                "form": "A",
                                "name": "架空様式",
                                "use": True,
                                "fields": [{"status": "値あり", "basis": 0}, {"status": "値あり"}, {"status": "空欄"}],
                            }
                        ],
                    },
                    {"person": "p-b", "tax_year": 2026, "ok": False, "reason": "未確定がある", "forms": []},
                ],
                "filing": {
                    "entries": [{}, {}, {}],
                    "withheld": [
                        {"person": "p-a", "time": Y2026, "reasons": ["未確定"], "concept": "所得税.申告納税額", "value_id": "v-9", "extra": "drop"},
                        {"person": "p-b", "time": Y2026, "reasons": ["未確定"], "concept": "所得税.申告納税額", "value_id": "v-10"},
                    ],
                },
            },
            {"id": "alt", "label": "架空の別案", "values": [], "differences": [{}, {}]},
        ],
    }


def raw_result() -> dict[str, Any]:
    """本物の evaluate の JSON の形に似せた、小さな架空の結果（毎回新しい写し）。"""
    return copy.deepcopy(_raw_result())


META = {
    "ledger": [
        {
            "kind": "判断.生計を一にするか",
            "section": "judgments",
            "subject": ["person"],
            "when": "period",
            "value": {"type": "boolean"},
            "title": "生計を一にするか",
        },
        {
            "kind": "選択.扶養の所属",
            "section": "choices",
            "subject": ["dependent"],
            "when": "tax_year",
            "value": {"type": "object"},
            "title": "どちらの扶養に入れるか",
        },
        {
            "kind": "見込み.年間収入",
            "section": "judgments",
            "subject": ["person"],
            "when": "fiscal_year",
            "value": {"type": "string"},
            "mark": "予測",
            "title": "年間収入の見込み",
        },
        {
            "kind": "判断.住所の所在",
            "section": "judgments",
            "subject": ["person"],
            "when": "on",
            "value": {"type": "string"},
            "title": "住所の所在",
        },
    ]
}
