"""
MCP tool registry: schema translation and dispatch.

Pure logic — no MCP SDK imports here, so this module is fully
unit-testable without the optional ``mcp`` dependency installed.

Tool names from MCP servers are namespaced ``mcp__{server}__{tool}`` so
provenance is visible in permission prompts and collisions with core
tools are impossible.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# OpenAI function-name constraint.
_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")
_MAX_NAME_LEN = 64

# Tool results larger than this are truncated before going back to the LLM.
MAX_RESULT_CHARS = 20_000


@dataclass
class McpToolSpec:
    """One tool discovered from an MCP server, ready for LLM registration."""
    server: str            # config key, e.g. "mongodb"
    name: str              # original MCP tool name, e.g. "find"
    qualified: str         # "mcp__mongodb__find"
    description: str
    input_schema: dict = field(default_factory=dict)

    def to_openai_format(self) -> dict:
        schema = self.input_schema or {"type": "object", "properties": {}}
        return {
            "type": "function",
            "function": {
                "name": self.qualified,
                "description": f"[MCP:{self.server}] {self.description}".strip(),
                "parameters": schema,
            },
        }


def sanitize(name: str) -> str:
    """Replace characters not allowed in OpenAI function names with '_'."""
    return _NAME_RE.sub("_", name)


def qualify(server: str, tool: str, taken: set[str]) -> str:
    """Build a unique, length-limited qualified name for *tool* on *server*."""
    base = f"mcp__{sanitize(server)}__{sanitize(tool)}"
    if len(base) > _MAX_NAME_LEN:
        base = base[:_MAX_NAME_LEN]
    candidate = base
    suffix = 2
    while candidate in taken:
        tail = f"_{suffix}"
        candidate = base[: _MAX_NAME_LEN - len(tail)] + tail
        suffix += 1
    if candidate != f"mcp__{server}__{tool}":
        logger.debug("MCP tool name mapped: %s/%s -> %s", server, tool, candidate)
    return candidate


class McpRegistry:
    """Holds discovered tool specs and builds dispatch handlers.

    ``call_fn(server, tool, args) -> str`` is injected (the bridge's sync
    facade) so this module stays free of threading/SDK concerns.
    """

    def __init__(self, call_fn: Callable[[str, str, dict], str]):
        self._call_fn = call_fn
        self.specs: list[McpToolSpec] = []
        self._taken: set[str] = set()

    def add_server_tools(
        self, server: str, tools: list[tuple[str, str, dict]]
    ) -> list[McpToolSpec]:
        """Register (name, description, input_schema) tuples from one server."""
        added = []
        for name, description, input_schema in tools:
            qualified = qualify(server, name, self._taken)
            self._taken.add(qualified)
            spec = McpToolSpec(
                server=server,
                name=name,
                qualified=qualified,
                description=description or "",
                input_schema=input_schema or {},
            )
            self.specs.append(spec)
            added.append(spec)
        return added

    def get_registrations(self) -> list[tuple[McpToolSpec, Callable[[dict], str]]]:
        """(spec, handler) pairs for tools.py to append to its registry."""
        return [(spec, self._make_handler(spec)) for spec in self.specs]

    def _make_handler(self, spec: McpToolSpec) -> Callable[[dict], str]:
        def handler(**kwargs: Any) -> str:
            return self._call_fn(spec.server, spec.name, kwargs)
        handler.__name__ = spec.qualified
        return handler


def flatten_result(result: Any) -> str:
    """Render an MCP CallToolResult (duck-typed) as a single string.

    Handles text / image / audio / resource content blocks and the
    ``isError`` flag. Output is truncated to MAX_RESULT_CHARS.
    """
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        btype = getattr(block, "type", "")
        if btype == "text":
            parts.append(getattr(block, "text", ""))
        elif btype in ("image", "audio"):
            mime = getattr(block, "mimeType", "unknown")
            data = getattr(block, "data", "") or ""
            parts.append(f"[{btype} content omitted — {mime}, {len(data)} bytes base64]")
        elif btype == "resource":
            res = getattr(block, "resource", None)
            uri = getattr(res, "uri", "") if res else ""
            text = getattr(res, "text", "") if res else ""
            parts.append(f"[resource {uri}]\n{text}".strip())
        else:
            parts.append(f"[unsupported content type: {btype}]")
    out = "\n".join(p for p in parts if p) or "(empty result)"
    if len(out) > MAX_RESULT_CHARS:
        out = out[:MAX_RESULT_CHARS] + "\n…[truncated]"
    if getattr(result, "isError", False):
        return f"Error from MCP server: {out}"
    return out
