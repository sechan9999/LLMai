"""
The ``recall_memory`` tool — exposes the memory store to the agent.

Mirrors the shape a MongoDB Atlas MCP Server would offer: a single
semantic-search call over prior sessions and extracted knowledge,
scoped to the current workspace.
"""
from __future__ import annotations

from typing import Any

from . import get_store

TOOL_DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "recall_memory",
        "description": (
            "Search prior sessions and extracted knowledge in this workspace "
            "for content semantically related to the query. Use BEFORE writing "
            "new code if you suspect you've seen this problem before. Returns "
            "ranked snippets with timestamps. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language question or topic to search for",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum hits to return (default 5)",
                },
                "scope": {
                    "type": "string",
                    "description": "summaries | knowledge | both (default both)",
                },
            },
            "required": ["query"],
        },
    },
}


def recall_memory(query: str, limit: int = 5, scope: str = "both") -> str:
    """Search the memory store and return a formatted snippet list."""
    store = get_store()
    if store is None or not store.connected:
        return "Error: memory store not configured or unreachable."

    # Workspace is resolved lazily via the tools module so the scoping
    # tracks whatever workspace_root was set for this process.
    from ..tools import WORKSPACE_ROOT

    if scope not in ("summaries", "knowledge", "both"):
        return f"Error: invalid scope '{scope}'. Use summaries | knowledge | both."

    try:
        hits = store.recall(
            query=query,
            workspace_path=str(WORKSPACE_ROOT),
            scope=scope,
            limit=max(1, min(int(limit or 5), 20)),
        )
    except Exception as e:
        return f"Error in recall_memory: {e}"

    if not hits:
        return f"No prior memory matches for: {query}"

    lines: list[str] = [f"Found {len(hits)} memory hit(s) for: {query}"]
    for i, h in enumerate(hits, 1):
        when = h.get("created_at")
        when_str = when.strftime("%Y-%m-%d") if when else "?"
        scope_tag = h.get("scope", "?")
        kind = h.get("kind") or ""
        score = h.get("score", 0.0)
        score_tag = f" score={score:.2f}" if score else ""
        prefix = f"[{i}] {scope_tag}{'/' + kind if kind else ''} · {when_str}{score_tag}"
        body = (h.get("text") or "").strip()
        if len(body) > 600:
            body = body[:600] + "…"
        lines.append(f"{prefix}\n    {body}")
    return "\n\n".join(lines)
