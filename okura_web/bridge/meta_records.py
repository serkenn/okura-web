"""記録層の仮想環境で動かす：中間表現の語彙（種類・書く場所・欄のスキーマ）を JSON で標準出力に書く。

起動：<records の python> -I -X utf8 meta_records.py
okura-web の Web サーバーはこれを import しない（サブプロセスとして起動して JSON を受け取る）。
家族のデータは読まない。
"""

import json
import sys

from okura_ir import SCHEMA_VERSION, load_schema
from okura_ir import vocabulary as irv
from okura_records import ledger_map


def _fields(mapping):
    return {name: {"schema": f.schema, "required": f.required} for name, f in mapping.items()}


def main() -> int:
    placements = {p.kind: {"section": p.section, "place": p.primary, "also": list(p.also)} for p in ledger_map.PLACEMENTS}
    records = []
    for section, kinds in irv.RECORD_SECTIONS.items():
        for k in kinds:
            records.append(
                {
                    "section": section,
                    "kind": k.kind,
                    "vocab": k.vocab,
                    "title": k.title,
                    "roles": dict(k.roles),
                    "when": k.when,
                    "amounts": _fields(k.amounts),
                    "attributes": _fields(k.attributes),
                    "place": placements.get(k.kind, {}).get("place"),
                }
            )
    ledger = []
    for section, kinds in irv.LEDGER_SECTIONS.items():
        for k in kinds:
            ledger.append(
                {
                    "section": section,
                    "kind": k.kind,
                    "vocab": k.vocab,
                    "title": k.title,
                    "subject": _fields(k.subject),
                    "when": k.when,
                    "value": k.value,
                    "mark": k.mark,
                }
            )
    schema = load_schema()
    out = {
        "ir_schema_version": SCHEMA_VERSION,
        "records": records,
        "ledger": ledger,
        "defs": schema.get("$defs", {}),
        "marks": list(irv.MARKS),
        "expense_categories": dict(irv.EXPENSE_CATEGORIES),
        "not_used_in_calculation": sorted(irv.NOT_USED_IN_CALCULATION),
    }
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
