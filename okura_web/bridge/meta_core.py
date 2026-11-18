"""判定コアの仮想環境で動かす：注入点の一覧・対象の年分・根拠の種類を JSON で標準出力に書く。

起動：<core の python> -I -X utf8 meta_core.py
家族のデータは読まない。
"""

import dataclasses
import json
import sys

from okura_core import injection_points, timepoints
from okura_core.basis import SourceKind


def _field(f):
    return {
        "name": f.name,
        "kind": f.kind,
        "title": f.title,
        "required": f.required,
        "values": list(f.values),
        "fields": [_field(x) for x in f.fields],
    }


def main() -> int:
    points = []
    for name, p in injection_points.POINTS.items():
        points.append(
            {
                "name": name,
                "institution": p.institution,
                "title": p.title,
                "issuer_kinds": list(p.issuer_kinds),
                "fields": [_field(f) for f in p.fields],
                "timing": p.timing,
                "references": list(p.references),
                "candidates": [
                    {"label": c.label, "data": c.data, "references": list(c.references), "note": c.note} for c in p.candidates
                ],
                "candidates_note": p.candidates_note,
                "note": p.note,
            }
        )
    try:
        from okura_core import __version__ as core_version
    except ImportError:  # 版の名前がないとき
        core_version = None
    out = {
        "okura_core": core_version,
        "injection_points": points,
        "supported": {
            "income_tax_years": list(timepoints.SUPPORTED_INCOME_TAX_YEARS),
            "fiscal_years": list(timepoints.SUPPORTED_FISCAL_YEARS),
            "judgment_dates": [d.isoformat() for d in timepoints.SUPPORTED_JUDGMENT_DATES],
        },
        "source_kinds": [k.value for k in SourceKind],
    }
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
