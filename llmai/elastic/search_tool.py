"""
The ``search_knowledge`` tool — hybrid search over org knowledge.

Shape mirrors the contract the official Elasticsearch MCP Server exposes,
so a future swap to a real MCP transport is a one-file change.
"""
from __future__ import annotations

from typing import Any

from . import get_client

TOOL_DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_knowledge",
        "description": (
            "Hybrid semantic + keyword search over organizational knowledge: "
            "GitLab issues, project docs. Use BEFORE writing code that "
            "touches an error path or external API — checks for prior issues "
            "and design decisions you may not have seen. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language search query",
                },
                "scope": {
                    "type": "string",
                    "description": "issues | docs | both (default both)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max hits to return (1-20, default 5)",
                },
            },
            "required": ["query"],
        },
    },
}


def search_knowledge(query: str, scope: str = "both", limit: int = 5) -> str:
    """Hybrid search the Elastic indices, return a formatted snippet list."""
    client = get_client()
    if client is None or not client.connected:
        return "Error: Elastic not configured or unreachable."
    if scope not in ("issues", "docs", "both"):
        return f"Error: invalid scope '{scope}'. Use issues | docs | both."

    try:
        hits = client.hybrid_search(
            query=query,
            scope=scope,
            limit=max(1, min(int(limit or 5), 20)),
        )
    except Exception as e:
        return f"Error in search_knowledge: {e}"

    if not hits:
        return f"No knowledge matches for: {query}"

    lines: list[str] = [f"Found {len(hits)} hit(s) for: {query}"]
    for i, h in enumerate(hits, 1):
        score = h.get("score") or 0.0
        title = (h.get("title") or "").strip() or "(untitled)"
        idx = h.get("index", "?")
        url = h.get("url") or ""
        state = h.get("state")
        labels = h.get("labels")
        meta_bits: list[str] = []
        if state:
            meta_bits.append(f"state={state}")
        if labels:
            meta_bits.append(f"labels={','.join(labels[:3])}")
        if url:
            meta_bits.append(url)
        meta = " · ".join(meta_bits)
        snippet = (h.get("snippet") or "").strip()
        if len(snippet) > 500:
            snippet = snippet[:500] + "…"
        head = f"[{i}] {idx} · score={score:.2f}\n    {title}"
        if meta:
            head += f"\n    {meta}"
        lines.append(f"{head}\n    {snippet}" if snippet else head)
    return "\n\n".join(lines)
