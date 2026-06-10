# mcp-integration Planning Document

> **Summary**: Add a real MCP client to LLMai so partner integrations (MongoDB Atlas, Elasticsearch) run through official MCP servers — satisfying the hackathon's "partner integration using MCP" requirement.
>
> **Project**: llmai-agent (LLMai)
> **Version**: 0.2.3 → targets 0.3.0
> **Author**: sechan9999
> **Date**: 2026-06-09
> **Status**: Draft

---

## 1. Overview

### 1.1 Purpose

The hackathon brief requires "a meaningful integration with at least one participating partner's solution **using MCP**." LLMai currently integrates partners (MongoDB Atlas, Elastic, Dynatrace) through direct SDK clients (`pymongo`, `elasticsearch`), and the README only claims "MCP-compatible tool *shapes*." This feature adds an actual MCP client so the agent discovers and calls tools exposed by official partner MCP servers — turning the claim into a verifiable fact.

### 1.2 Background

- Devpost submission: "Enterprise AI without leaks or overspending"
- Gap analysis (2026-06-09): 3/5 hackathon requirements met; MCP integration and Gemini/Agent Builder are the gaps
- MCP fits the local-first story: MCP servers run locally via stdio, so no data leaves the machine
- Existing tool registry already supports conditional registration ([llmai/tools.py](../../../llmai/tools.py)) — MCP tools slot into the same mechanism

### 1.3 Related Documents

- Hackathon brief: https://devpost.com/software/enterprise-ai-without-leaks-or-overspending
- MCP spec: https://modelcontextprotocol.io
- MongoDB MCP server: https://github.com/mongodb-js/mongodb-mcp-server
- Elastic MCP: https://github.com/elastic/mcp-server-elasticsearch

---

## 2. Scope

### 2.1 In Scope

- [ ] `llmai/mcp/` package: MCP client over **stdio transport** (local subprocess servers)
- [ ] Tool discovery: `tools/list` from connected servers → registered into the agent's tool registry with server-namespaced names (e.g. `mcp__mongodb__find`)
- [ ] Tool invocation: `tools/call` routed through the existing `execute_tool` dispatch
- [ ] Permission mapping: MCP tools default to `ask`; per-tool overrides in config
- [ ] Config: `"mcp": { "servers": { name: { command, args, env } } }` in `config.json` + env var equivalents
- [ ] MongoDB official MCP server wired as the primary partner demo (memory recall path)
- [ ] Elastic MCP server wired as second partner (knowledge search path)
- [ ] Optional dependency group `[mcp]` in pyproject (`mcp>=1.0` Python SDK)
- [ ] Unit tests with an in-process mock MCP server (offline-friendly, no live backends)
- [ ] `docs/mcp-setup.md` + README section; fix the "MCP-compatible" wording

### 2.2 Out of Scope

- Exposing LLMai itself *as* an MCP server (stretch goal, separate feature)
- HTTP/SSE remote transport (stdio only for v1)
- Removing the existing direct `pymongo`/`elasticsearch` integrations (kept as fallback; MCP mode is opt-in like the other layers)
- Google Cloud Agent Builder hybrid orchestration (separate feature: `agent-builder-hybrid`)
- Dynatrace via MCP (no suitable official local MCP server; OTel path stays as-is)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | Agent connects to ≥1 MCP server via stdio at startup when `LLMAI_MCP_ENABLED=true` | High | Pending |
| FR-02 | Tools listed by MCP servers appear in the LLM's tool definitions (OpenAI function format) | High | Pending |
| FR-03 | MCP tool calls route through the permission gate (`allow`/`ask`/`deny`) before execution | High | Pending |
| FR-04 | MongoDB MCP server integration works end-to-end (connect → list → call → result to LLM) | High | Pending |
| FR-05 | Elastic MCP server integration works end-to-end | Medium | Pending |
| FR-06 | Server connection failure degrades gracefully: warning logged, agent runs without those tools | High | Pending |
| FR-07 | `llmai-doctor` reports MCP server connectivity status | Medium | Pending |
| FR-08 | Both CLI (sync) and Web UI (async) loops can invoke MCP tools | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|--------------------|
| Privacy | No MCP traffic leaves localhost in default config (stdio subprocess) | Code review + docs threat-model table |
| Reliability | MCP server crash mid-session does not crash the agent loop | Unit test: kill mock server, assert error string returned as tool result |
| Performance | Tool discovery adds < 2s to startup per server | Timed in `llmai-doctor` |
| Compatibility | Core install unaffected — `mcp` stays an optional extra | CI: core tests pass without `mcp` installed |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] All High-priority FRs implemented
- [ ] Unit tests pass offline (mock MCP server); integration tests behind `-m integration`
- [ ] Demo script: agent answers "what did we decide about X last week?" via MongoDB MCP tools
- [ ] README + `docs/mcp-setup.md` updated; "MCP-compatible shapes" wording replaced with real claim
- [ ] Devpost submission text updated to point at the MCP integration

### 4.2 Quality Criteria

- [ ] CI green on ubuntu + windows, py3.10 + 3.12
- [ ] Zero ruff errors
- [ ] Wheel smoke test still passes (no new packaging regressions)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Official MongoDB/Elastic MCP servers are Node-based → requires `npx` at runtime | Medium | High | Document Node ≥18 prerequisite; `llmai-doctor` checks for it; graceful degradation (FR-06) |
| MCP Python SDK is async-only; CLI loop is sync | Medium | High | Run MCP client on a background event loop thread; sync facade for `agent.py` |
| Tool name collisions between MCP servers and core tools | Medium | Medium | Namespace all MCP tools `mcp__{server}__{tool}` |
| Remote tools are uninspected code paths (security) | High | Medium | Default permission `ask` for every MCP tool; explicit allowlist in config to auto-approve |
| Hackathon deadline pressure | High | Medium | FR-04 (MongoDB path) alone satisfies "≥1 partner via MCP" — ship that first, Elastic second |

---

## 6. Architecture Considerations

### 6.1 Project Level

Existing project — **Dynamic** level Python package (no change). New code is an optional subsystem mirroring the existing `llmai/memory/` and `llmai/elastic/` layer pattern.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| MCP SDK | official `mcp` Python SDK / hand-rolled JSON-RPC | `mcp` SDK | Spec-tracking, typed, maintained by Anthropic |
| Transport | stdio / HTTP+SSE / streamable HTTP | stdio | Local-first story; servers run as subprocesses; zero network exposure |
| Tool naming | flat / prefixed | `mcp__{server}__{tool}` | Collision-proof; provenance visible to user in permission prompts |
| Sync bridge | asyncio.run per call / background loop thread | background loop thread | Avoids event-loop conflicts with FastAPI; one persistent session per server |
| Dependency | core / optional extra | optional `[mcp]` extra | Consistent with `[memory]`, `[elastic]`, `[telemetry]` pattern |
| Permission default | allow / ask | `ask` | Remote tools are untrusted by default; config allowlist for read-only ones |

### 6.3 Module Layout

```
llmai/mcp/
├── __init__.py        # is_enabled(), get_clients() — same pattern as memory/, elastic/
├── client.py          # McpServerConnection: spawn, handshake, tools/list, tools/call
├── bridge.py          # background event loop thread + sync facade
└── registry.py        # MCP tool specs → OpenAI function format, dispatch hook
```

---

## 7. Convention Prerequisites

### 7.1 Existing Conventions (verified)

- [x] ruff configured (`pyproject.toml`, line-length 100, E/F/W/I)
- [x] Optional-dependency pattern established (`[memory]`, `[elastic]`, `[telemetry]`)
- [x] Conditional tool registration pattern in `llmai/tools.py`
- [x] Test layout: offline unit tests in `tests/`, live tests in `tests/integration/` behind `-m integration`
- [ ] No TypeScript/ESLint concerns (Python-only feature)

### 7.2 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `LLMAI_MCP_ENABLED` | Master switch for MCP layer | Agent | ☐ |
| `LLMAI_MCP_CONFIG` | Path to MCP servers config (default: `config.json` `mcp` key) | Agent | ☐ |
| `MDB_MCP_CONNECTION_STRING` | Passed through to MongoDB MCP server subprocess | Subprocess env | ☐ |
| `ES_URL` / `ES_API_KEY` | Passed through to Elastic MCP server subprocess | Subprocess env | ☐ |

---

## 8. Next Steps

1. [ ] Write design document (`mcp-integration.design.md`) — `/pdca design mcp-integration`
2. [ ] Verify with organizers whether MongoDB-via-MCP alone satisfies "Partner Power"
3. [ ] Start implementation (FR-04 MongoDB path first)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-09 | Initial draft from hackathon gap analysis | sechan9999 + Claude |
