"""リモートの MCP サーバー（Streamable HTTP。POST /mcp に JSON-RPC、応答は application/json）。

- 認証はエージェントのトークン（`Authorization: Bearer okt_…`。ヘッダーを送れないクライアントは `?token=okt_…`）。
- 道具は tools.py と同じ（読む・計算する・説明する・提案する）。確定（台帳への書き込み）はできない。
- トークンが外部向けなら、伏せ字と同意のない人の除外がかかる（access.redact_record と external_ai）。
- 状態は持たない（セッション ID を使わない）。
"""

from __future__ import annotations

import json
from typing import Any

from .app import App
from .tools import ToolError, call, context_for, specs

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "okura-web", "version": "0.1.0"}
INSTRUCTIONS = (
    "okura-web は家族の税・社会保険の記録と、okura-gov（法令の関数）の計算結果を扱う。最初に household_overview を呼ぶ。"
    "計算は run_calculation（30秒ほど）→ calculation_status → calculation_summary。未確定は list_questions で答えごとの違いを見る。"
    "人が決めること（質問への回答）は propose_judgment で提案するだけで、登録は人が画面で行う。"
    "結果を丸めない・推奨しない（税務の助言をしない）。申告書の欄の値は人が作成コーナーに入力する。"
)


def _ok(mid: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def handle_message(app: App, principal: Any, msg: Any) -> dict[str, Any] | None:
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _err(None, -32600, "JSON-RPC 2.0 の形でない")
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}
    if mid is None:
        return None  # 通知
    if method == "initialize":
        want = params.get("protocolVersion")
        return _ok(mid, {
            "protocolVersion": want if want in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS,
        })
    if method == "ping":
        return _ok(mid, {})
    if method == "tools/list":
        cats = tuple(c for c in ("read", "compute", "explain") if "read" in principal.scopes) + (("propose",) if "propose" in principal.scopes else ())
        return _ok(mid, {"tools": [
            {
                "name": t["name"],
                "description": f"[{t['category']}] {t['description']}",
                "inputSchema": t["input_schema"],
                "annotations": {"readOnlyHint": t["category"] != "propose", "destructiveHint": False, "openWorldHint": False},
            }
            for t in specs(cats)
        ]})
    if method == "tools/call":
        name = str(params.get("name", ""))
        args = params.get("arguments") or {}
        ctx = context_for(app, principal, external=principal.external, origin=f"mcp:{principal.token_id}")
        try:
            result = call(ctx, name, args if isinstance(args, dict) else {})
        except ToolError as e:
            return _ok(mid, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        app.db.audit(principal.household_id, principal.actor, f"mcp:{name}")
        text = json.dumps(result, ensure_ascii=False, default=str)
        return _ok(mid, {"content": [{"type": "text", "text": text}], "isError": False})
    if method in ("resources/list", "prompts/list", "resources/templates/list"):
        key = {"resources/list": "resources", "prompts/list": "prompts", "resources/templates/list": "resourceTemplates"}[method]
        return _ok(mid, {key: []})
    return _err(mid, -32601, f"知らない method: {method}")


def handle_body(app: App, principal: Any, body: Any) -> tuple[int, Any]:
    """(HTTP の状態, 応答の本体)。通知だけなら 202 と None。"""
    if isinstance(body, list):
        out = [r for r in (handle_message(app, principal, m) for m in body) if r is not None]
        return (200, out) if out else (202, None)
    r = handle_message(app, principal, body)
    return (200, r) if r is not None else (202, None)
