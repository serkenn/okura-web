"""MCP の接続先の一覧（手順と公式アイコン）を frontend/src/lib/mcp_clients.js に書き出す。

    .work/venvs/web/Scripts/python.exe -I -X utf8 tools/build_mcp_clients.py .work/scratch/mcp_clients.json

アイコンはダウンロードした SVG から取り出したパスだけを使う。形を厳しく検査し（パスの命令と数字、色、viewBox）、
それ以外の属性・要素（スクリプト・外部参照・スタイル）は入れない。文字は画面で textContent として出す。
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D_OK = re.compile(r"^[MmLlHhVvCcSsQqTtAaZz0-9 .,eE+\-\n\t]{1,20000}$")
FILL_OK = re.compile(r"^(#[0-9a-fA-F]{3,8}|currentColor|none|white|black)$")
VB_OK = re.compile(r"^-?[\d.]+ -?[\d.]+ [\d.]+ [\d.]+$")
ID_OK = re.compile(r"^[a-z0-9-]{1,40}$")

LOCAL = {
    "id": "local",
    "name": "このパソコン（ローカル）",
    "headers": True,
    "steps": [
        "okura-web を動かしているパソコンで、AI アプリの MCP の設定ファイルを開く",
        "下の設定を貼り、AI アプリを起動し直す",
    ],
    "fields": [],
    "snippet": {
        "lang": "json",
        "file": "claude_desktop_config.json など",
        "text": json.dumps({"mcpServers": {"okura-web": {
            "command": "{PYTHON}",
            "args": ["-I", "-X", "utf8", "{MCP_SERVER}"],
            "env": {"OKURA_WEB_URL": "http://127.0.0.1:8765", "OKURA_WEB_TOKEN": "{TOKEN}"},
        }}}, ensure_ascii=False, indent=2),
    },
    "docs": None,
    "icon": {"viewBox": "0 0 24 24", "paths": [{"d": "M3 4h18a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1h-7v2h3v2H7v-2h3v-2H3a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zm1 2v9h16V6z", "fill": "#44403c", "fill-rule": "evenodd"}]},
}


def clean_text(s, limit=600):
    if not isinstance(s, str):
        return ""
    s = "".join(ch for ch in s if ch == "\n" or ord(ch) >= 32)
    return s[:limit]


def clean(c):
    if not isinstance(c, dict) or not ID_OK.match(str(c.get("id", ""))):
        return None
    out = {
        "id": c["id"],
        "name": clean_text(c.get("name"), 40),
        "headers": bool(c.get("headers")),
        "steps": [clean_text(x, 200) for x in (c.get("steps") or [])][:8],
        "fields": [{"label": clean_text(f.get("label"), 40), "value": clean_text(f.get("value"), 300)} for f in (c.get("fields") or []) if isinstance(f, dict)][:6],
        "snippet": None,
        "docs": c.get("docs") if isinstance(c.get("docs"), str) and c["docs"].startswith("https://") else None,
        "icon": None,
    }
    sn = c.get("snippet")
    if isinstance(sn, dict) and sn.get("text"):
        out["snippet"] = {"lang": clean_text(sn.get("lang"), 10), "file": clean_text(sn.get("file"), 80), "text": clean_text(sn.get("text"), 3000)}
    ic = c.get("icon")
    if isinstance(ic, dict) and VB_OK.match(str(ic.get("viewBox", ""))):
        paths = []
        for p in ic.get("paths") or []:
            d = str(p.get("d", ""))
            fill = str(p.get("fill") or "currentColor")
            if not D_OK.match(d) or not FILL_OK.match(fill):
                paths = []
                break
            item = {"d": " ".join(d.split()), "fill": fill}
            if p.get("fill-rule") in ("evenodd", "nonzero"):
                item["fill-rule"] = p["fill-rule"]
            paths.append(item)
        if paths:
            out["icon"] = {"viewBox": ic["viewBox"], "paths": paths}
    return out


def main(src):
    data = json.loads(Path(src).read_text(encoding="utf-8-sig"))
    clients = [x for x in (clean(c) for c in data) if x]
    clients.append(clean(LOCAL) or LOCAL)
    body = json.dumps(clients, ensure_ascii=False, indent=1)
    js = "// MCP の接続先（tools/build_mcp_clients.py が作る。手で直さない）\nexport const CLIENTS = " + body + ";\n"
    (ROOT / "frontend" / "src" / "lib" / "mcp_clients.js").write_text(js, encoding="utf-8", newline="\n")
    print(f"{len(clients)} clients, icons: {sum(1 for c in clients if c['icon'])}")


if __name__ == "__main__":
    main(sys.argv[1])
