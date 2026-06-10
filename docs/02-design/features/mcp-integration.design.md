# mcp-integration Design Document

> **Summary**: Spec for `llmai/mcp/` — an MCP client subsystem (stdio transport) that discovers tools from official partner MCP servers (MongoDB, Elastic) and registers them into the existing tool registry behind the permission gate.
>
> **Project**: llmai-agent (LLMai)
> **Version**: 0.2.3 → targets 0.3.0
> **Author**: sechan9999
> **Date**: 2026-06-09
> **Status**: Draft
> **Planning Doc**: [mcp-integration.plan.md](../../01-plan/features/mcp-integration.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. The agent can call tools served by any spec-compliant MCP server over stdio, with zero changes to the agent loops (`llmai/agent.py`, `server/agent_ws.py`).
2. MCP follows the exact integration pattern already proven by `llmai/memory/` and `llmai/elastic/`: opt-in `init()` → `is_enabled()` → `register_mcp_tools()` → permission defaults dict.
3. Failure of any MCP server never crashes the agent — tools simply don't appear, or calls return error strings.

### 1.2 Design Principles

- **Pattern symmetry**: a maintainer who has read `llmai/elastic/__init__.py` should find `llmai/mcp/__init__.py` boring.
- **Sync facade over async core**: the MCP SDK is asyncio-only; all complexity is confined to `bridge.py`. Everything outside sees plain sync functions.
- **Untrusted by default**: MCP tools are remote code paths; default permission is `ask`, namespaced names make provenance visible in permission prompts.
- **Lazy imports**: importing `llmai.mcp` must never fail when the `mcp` package isn't installed (same rule as elastic/memory).

---

## 2. Architecture

### 2.1 Component Diagram

```
                    llmai/tools.py
                    ┌──────────────────────────────┐
 Agent loops ──────▶│ TOOL_DEFINITIONS             │
 (CLI sync /        │ execute_tool(name, args) ────┼──┐
  WS async via      └──────────────────────────────┘  │ name starts with "mcp__"
  run_in_executor)                                    ▼
                    llmai/mcp/registry.py ── sync call ──▶ llmai/mcp/bridge.py
                    (spec translation,                     (background asyncio
                     dispatch)                              loop thread)
                                                               │ MCP session (JSON-RPC)
                                              ┌────────────────┼────────────────┐
                                              ▼                ▼                ▼
                                       mongodb-mcp-server   mcp-server-      (any other
                                       (npx subprocess)     elasticsearch    configured
                                                            (npx subprocess)  server)
```

### 2.2 Data Flow

**Startup** (entry points `llmai/main.py` and `server/app.py`, after `memory.init()` / `elastic.init()`):

```
mcp.init(config)
  → bridge starts daemon thread + event loop
  → for each configured server: spawn subprocess, MCP initialize handshake, tools/list
  → registry converts MCP tool schemas → OpenAI function format,
    names rewritten to mcp__{server}__{tool}
  → tools.register_mcp_tools() appends definitions + handlers
```

**Tool call**:

```
LLM emits tool_call "mcp__mongodb__find"
  → permission gate (PermissionManager.check) — default "ask"
  → execute_tool → handler in _BASE_HANDLERS
  → registry.dispatch(server="mongodb", tool="find", args)
  → bridge: asyncio.run_coroutine_threadsafe(session.call_tool(...), loop).result(timeout)
  → MCP result content blocks → flattened to string → returned to LLM
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `llmai/mcp/__init__.py` | nothing heavy (lazy) | `init()`, `is_enabled()`, `shutdown()`, `MCP_DEFAULT_PERMISSIONS` |
| `llmai/mcp/bridge.py` | `mcp` SDK (lazy), `threading`, `asyncio` | event-loop thread, session lifecycle, sync facade |
| `llmai/mcp/client.py` | `mcp` SDK (lazy) | per-server connection: spawn, handshake, list, call |
| `llmai/mcp/registry.py` | stdlib only | schema translation, name namespacing, dispatch table |
| `llmai/tools.py` | `llmai.mcp` (lazy, inside function) | `register_mcp_tools()` — same shape as `register_memory_tool()` |
| `llmai/permissions.py` | `llmai.mcp` (import-safe dict) | merge `MCP_DEFAULT_PERMISSIONS` into `DEFAULT` |
| `llmai/doctor.py` | `llmai.mcp` | connectivity + Node.js prerequisite check |

New optional dependency in pyproject: `mcp = ["mcp>=1.0"]`.

---

## 3. Data Model

### 3.1 Config Schema (`config.json` `mcp` block)

```json
{
  "mcp": {
    "enabled": false,
    "call_timeout_s": 30,
    "servers": {
      "mongodb": {
        "command": "npx",
        "args": ["-y", "mongodb-mcp-server", "--readOnly"],
        "env": { "MDB_MCP_CONNECTION_STRING": "${LLMAI_MEMORY_URI}" },
        "allow": ["find", "aggregate", "list-collections"]
      },
      "elasticsearch": {
        "command": "npx",
        "args": ["-y", "@elastic/mcp-server-elasticsearch"],
        "env": { "ES_URL": "http://localhost:9200" },
        "allow": ["search", "list_indices", "get_mappings"]
      }
    }
  }
}
```

- Env var master switch: `LLMAI_MCP_ENABLED=true` (env always wins, per existing convention).
- `${VAR}` values in `env` are expanded from the parent process environment at spawn time; unset vars resolve to empty string with a logged warning.
- `allow`: tool names (un-namespaced) auto-approved for this server. Everything else defaults to `ask`.

### 3.2 Internal Types (`llmai/mcp/registry.py`)

```python
@dataclass
class McpToolSpec:
    server: str            # config key, e.g. "mongodb"
    name: str              # original MCP tool name, e.g. "find"
    qualified: str         # "mcp__mongodb__find"
    description: str
    input_schema: dict     # JSON Schema from tools/list (passed through)

@dataclass
class McpServerState:
    name: str
    status: Literal["connected", "failed", "disabled"]
    tools: list[McpToolSpec]
    error: str | None      # populated when status == "failed"
```

### 3.3 Name Mapping Rules

| MCP side | LLM side |
|----------|----------|
| server `mongodb`, tool `find` | `mcp__mongodb__find` |
| tool names with `-` or `.` | replaced with `_` (e.g. `list-collections` → `list_collections`) |
| collision after sanitizing | suffix `_2`, `_3`, … + warning log |

Qualified names must match `^[a-zA-Z0-9_-]{1,64}$` (OpenAI function-name constraint); truncate to 64 chars if needed, keeping the server prefix intact.

---

## 4. Interface Specification

### 4.1 Public API — `llmai/mcp/__init__.py`

| Function | Signature | Behavior |
|----------|-----------|----------|
| `init` | `init(config: dict \| None = None) -> bool` | Idempotent. Reads `mcp` block + env. Starts bridge, connects servers, populates registry. Returns `is_enabled()`. Never raises. |
| `is_enabled` | `() -> bool` | True when ≥1 server connected. |
| `get_server_states` | `() -> list[McpServerState]` | For doctor + `/mcp` CLI command. |
| `shutdown` | `() -> None` | Terminate subprocesses, stop loop thread. Registered via `atexit`; idempotent. |
| `MCP_DEFAULT_PERMISSIONS` | `dict[str, str]` | Empty at import time; populated during `init()` (see 4.3). |

### 4.2 Registration Hook — `llmai/tools.py`

```python
def register_mcp_tools() -> None:
    """Append all discovered MCP tools once mcp.init() succeeds.

    Same gate pattern as register_memory_tool — never expose a tool
    the agent can't actually use. Idempotent.
    """
    from . import mcp
    if not mcp.is_enabled():
        return
    for spec, handler in mcp.registry.get_registrations():
        if any(t["function"]["name"] == spec.qualified for t in TOOL_DEFINITIONS):
            continue
        TOOL_DEFINITIONS.append(spec.to_openai_format())
        _BASE_HANDLERS[spec.qualified] = handler
```

Entry-point call order (both `llmai/main.py` and `server/app.py`):
`memory.init()` → `elastic.init()` → `mcp.init()` → `register_mcp_tools()`.

### 4.3 Permission Integration

`PermissionManager` currently merges static dicts at import time. MCP tool names are only known after `init()`, so:

1. `permissions.py` does **not** import from `llmai.mcp` at module level (avoids the static-dict trap).
2. `mcp.init()` computes `{qualified_name: "allow" | "ask"}` from each server's `allow` list and calls a new `PermissionManager.merge_defaults(d: dict)` classmethod that updates `DEFAULT` before instances are created — and existing instances via a module-level registry update.
3. Simpler accepted trade-off for v1: entry points call `mcp.init()` **before** constructing `PermissionManager`, then pass `mcp.MCP_DEFAULT_PERMISSIONS` into the constructor as an extra-defaults argument (`PermissionManager(config_path, extra_defaults=...)`). This keeps `permissions.py` decoupled.

**Decision: option 3** — explicit, no global mutation, minimal diff.

### 4.4 Sync Bridge — `llmai/mcp/bridge.py`

```python
class McpBridge:
    def start(self) -> None            # spawn daemon thread, run loop forever
    def connect(self, name, cfg) -> McpServerState   # blocking, 10s handshake timeout
    def call(self, server, tool, args, timeout_s=30) -> str  # blocking facade
    def stop(self) -> None
```

- One `McpBridge` singleton; one persistent `ClientSession` per server.
- `call()` uses `asyncio.run_coroutine_threadsafe(...).result(timeout_s)`.
- WS loop already executes tools via `run_in_executor` ([server/agent_ws.py:312](../../../server/agent_ws.py)), so the blocking facade is safe in both loops with no event-loop conflict.

### 4.5 Result Flattening

MCP `tools/call` returns content blocks. Flattening rules:

| Block type | Rendering |
|-----------|-----------|
| `text` | verbatim, joined by `\n` |
| `image` / `audio` | `[{type} content omitted — {mimeType}, {size} bytes]` |
| `resource` | URI + text if embedded |
| `isError: true` | `Error from {server}: {flattened text}` |

Output truncated to 20,000 chars with `…[truncated]` marker (consistent with core tool output limits).

---

## 5. Error Handling

| Scenario | Behavior | User-visible result |
|----------|----------|---------------------|
| `mcp` package not installed but enabled | `init()` logs warning, returns False | doctor: "mcp extra not installed — pip install 'llmai-agent[mcp]'" |
| `npx`/command not found | server state `failed`, others continue | doctor: "Node.js ≥18 required for {server}" |
| Handshake timeout (10s) | server state `failed` | warning log; tools absent |
| Server crashes mid-session | one reconnect attempt; else calls return error string | `Error: MCP server 'mongodb' is not connected` |
| Tool call timeout | error string to LLM | `Error: mcp__mongodb__find timed out after 30s` |
| Tool returns `isError` | flattened per 4.5, returned as tool result | LLM sees error and can adapt |
| Unknown qualified name in dispatch | error string (existing `execute_tool` unknown-tool path) | `Error: Unknown tool` |

Rule: **no exception from `llmai/mcp/` may propagate into the agent loop.** Every public function catches and converts to log + return value.

---

## 6. Security Considerations

- [ ] Every MCP tool defaults to `ask`; auto-`allow` only via explicit per-server `allow` list in config
- [ ] Qualified names (`mcp__{server}__{tool}`) shown in permission prompts so the user sees provenance
- [ ] MongoDB server launched with `--readOnly` flag in the documented default config
- [ ] Subprocess env: only variables named in the server's `env` block are passed (no full env inheritance beyond PATH/system vars needed for npx)
- [ ] stdio transport only — no listening sockets opened by this feature
- [ ] Document in SECURITY.md threat-model table: MCP adds local subprocesses; data flows to whatever backend the MCP server itself connects to (e.g., Atlas cluster)

---

## 7. Test Plan

### 7.1 Test Scope

| Type | Target | Tool | Runs offline? |
|------|--------|------|:---:|
| Unit | registry: schema translation, name sanitizing, collisions, truncation | pytest | ✅ |
| Unit | bridge: call timeout, server-dead error path (mock session) | pytest + pytest-asyncio | ✅ |
| Unit | config parsing: env expansion, master switch, malformed block | pytest | ✅ |
| Unit | `register_mcp_tools` idempotency; permission defaults merge | pytest | ✅ |
| Integration | real handshake + tools/list + call against a **Python stub MCP server** (`tests/integration/mcp_stub_server.py`, runs via `python -m`, no Node needed) | pytest `-m integration` | ✅ (no live backend) |
| Integration | mongodb-mcp-server end-to-end | pytest `-m integration` | ❌ (needs Node + Atlas) |

### 7.2 Key Test Cases

- [ ] Happy path: stub server exposes 2 tools → both appear namespaced in `TOOL_DEFINITIONS`; call round-trips
- [ ] Error: server config with nonexistent command → state `failed`, `is_enabled()` False, core tools unaffected
- [ ] Error: call after server killed → error string, agent loop continues
- [ ] Edge: tool name `list-collections` → `mcp__mongodb__list_collections`; duplicate after sanitize → `_2` suffix
- [ ] Edge: `mcp` extra not installed → `import llmai.mcp` succeeds; `init()` returns False
- [ ] Permission: tool in `allow` list auto-approves; tool not listed prompts (`ask`)

---

## 8. Module Layout & Conventions

### 8.1 File Structure

```
llmai/mcp/
├── __init__.py     # init / is_enabled / shutdown / get_server_states / MCP_DEFAULT_PERMISSIONS
├── bridge.py       # McpBridge: daemon event-loop thread + sync facade
├── client.py       # McpServerConnection: spawn, handshake, tools/list, tools/call
└── registry.py     # McpToolSpec, name mapping, OpenAI-format conversion, dispatch

tests/
├── test_mcp_registry.py
├── test_mcp_bridge.py
├── test_mcp_config.py
└── integration/
    ├── mcp_stub_server.py
    └── test_mcp_e2e.py

docs/mcp-setup.md   # user-facing setup guide (mirrors atlas-setup.md structure)
```

### 8.2 Conventions Applied

| Item | Convention |
|------|-----------|
| Naming | snake_case functions, PascalCase classes, UPPER_SNAKE module constants (matches existing code) |
| Imports of `mcp` SDK | lazy, inside functions only |
| Logging | module-level `logger = logging.getLogger(__name__)`; warnings for degradation, never print |
| Lint | ruff E/F/W/I, line-length 100 |
| Docstrings | module docstring explaining opt-in behavior, same voice as `elastic/__init__.py` |

### 8.3 Implementation Order

1. [ ] `registry.py` — pure logic, fully unit-testable (no SDK needed)
2. [ ] `client.py` + `bridge.py` — SDK wiring, mock-based tests
3. [ ] `__init__.py` — init/config/env plumbing; pyproject `[mcp]` extra
4. [ ] `tools.py::register_mcp_tools` + `PermissionManager(extra_defaults=...)` + entry-point wiring
5. [ ] `doctor.py` MCP section (Node check, server states)
6. [ ] Stub-server integration test
7. [ ] `docs/mcp-setup.md` + README rewording + SECURITY.md threat-model row
8. [ ] Live MongoDB MCP demo script for Devpost video

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-09 | Initial design from plan FR-01..FR-08 | sechan9999 + Claude |
