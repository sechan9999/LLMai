"""
The ``query_logs`` tool — raw ES|QL over llmai's Elastic indices.

ES|QL is read-only (SELECT-like). The tool is permission-gated to ``ask``
because complex queries can be expensive on large indices.

Example queries:

  FROM llmai-pipeline-logs
    | WHERE @timestamp > NOW() - 7 days AND status == "failed"
    | STATS count = COUNT(*) BY error_signature, job_name
    | SORT count DESC
    | LIMIT 10

  FROM llmai-agent-logs
    | WHERE tool_name == "run_command" AND permission_outcome == "ask_deny"
    | KEEP @timestamp, tool_args_preview
    | LIMIT 20
"""
from __future__ import annotations

import json
from typing import Any

from . import get_client

TOOL_DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "query_logs",
        "description": (
            "Run an ES|QL (Elasticsearch Query Language) query against the "
            "llmai Elastic indices. Use for structured analysis of pipeline "
            "logs (llmai-pipeline-logs) or the agent's own behavior "
            "(llmai-agent-logs). Read-only; permission-gated since complex "
            "queries can be expensive."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "esql": {
                    "type": "string",
                    "description": (
                        "Full ES|QL query. Always start with FROM <index>. "
                        "Include LIMIT to cap result size."
                    ),
                },
            },
            "required": ["esql"],
        },
    },
}


def query_logs(esql: str) -> str:
    """Execute an ES|QL query, return a compact text rendering."""
    client = get_client()
    if client is None or not client.connected:
        return "Error: Elastic not configured or unreachable."

    result = client.run_esql(esql, max_rows=200)
    if result.get("error"):
        return f"ES|QL error: {result['error']}"

    cols = result.get("columns") or []
    rows = result.get("rows") or []
    truncated = result.get("truncated")

    if not cols and not rows:
        return "(no results)"

    headers = [c.get("name", "?") for c in cols]
    lines = [" | ".join(headers), "-" * min(len(" | ".join(headers)), 80)]
    for row in rows[:200]:
        rendered = []
        for cell in row:
            if cell is None:
                rendered.append("")
            elif isinstance(cell, (list, dict)):
                rendered.append(json.dumps(cell)[:60])
            else:
                s = str(cell)
                rendered.append(s[:60] + "…" if len(s) > 60 else s)
        lines.append(" | ".join(rendered))
    if truncated:
        lines.append("... (truncated at 200 rows; query returned more)")
    return "\n".join(lines)
