# mcp-integration Gap Analysis (Check Phase)

> **Design Doc**: [mcp-integration.design.md](../02-design/features/mcp-integration.design.md)
> **Date**: 2026-06-09
> **Method**: item-by-item comparison of design assertions vs implementation
> **Match Rate**: ~~92%~~ → **98% after Act-1** (44 full / 0 partial / 1 deferred of 45 items)

---

## 1. Section-by-Section Comparison

| Design section | Items | Result |
|---|---|---|
| §2 Architecture (modules, startup flow, call flow, dependencies) | 8 | ✅ all match |
| §3.1 Config schema (enabled, call_timeout_s, servers, `${VAR}` expansion, env-wins) | 6 | ✅ all match |
| §3.2 Internal types | 2 | ⚠️ 1 partial (GAP-5) |
| §3.3 Name mapping (namespace, sanitize, collision, 64-char limit) | 4 | ⚠️ 1 partial (GAP-2) |
| §4.1–4.4 Public API, registration hook, permissions, bridge | 12 | ✅ all match (incl. `extra_defaults` option 3, atexit, executor safety) |
| §4.5 Result flattening (text/image/audio/resource, isError, 20k truncation) | 5 | ✅ all match |
| §5 Error handling table (7 scenarios) | 7 | ✅ all match — verified by unit + e2e tests |
| §6 Security | 6 | ❌ 1 missing (GAP-1) |
| §7 Test plan | 6 rows | ⚠️ 1 partial (GAP-3), ❌ 1 missing (GAP-4: live MongoDB e2e) |
| §8 Layout & conventions | 5 | ✅ all match |

Verification evidence: 162 unit tests pass, 4 e2e tests pass against a real
MCP stdio handshake (stub server), ruff clean, doctor verified in
enabled/disabled states.

---

## 2. Gap List

### GAP-1 · Subprocess env inherits the full parent environment — **security, fix before release**

- **Design §6**: "only variables named in the server's `env` block are passed (no full env inheritance beyond PATH/system vars needed for npx)"
- **Implementation** ([llmai/mcp/client.py:96](../../llmai/mcp/client.py)): `env={**os.environ, **self.config.env}` when any env var is configured — every secret in the agent's environment (API keys, tokens) leaks into the MCP server subprocess.
- **Fix**: merge the MCP SDK's `get_default_environment()` (minimal safe env: PATH, HOME, etc.) with only the named vars.

### GAP-2 · `sanitize()` keeps dashes — minor, intentional deviation

- **Design §3.3**: tool names with `-` or `.` replaced with `_` (example: `list-collections` → `list_collections`).
- **Implementation**: keeps `-` because the OpenAI function-name charset allows it; only disallowed chars are replaced. Tests assert the implemented behavior.
- **Disposition**: implementation is more faithful to the upstream constraint than the design was. Recommend updating the design doc rather than the code.

### GAP-3 · Two unit tests from the design's test matrix are missing — minor

- "server config with nonexistent command → state `failed`, `is_enabled()` False, core tools unaffected" — covered only indirectly (bridge reconnect-failure test); no `init()`-level test.
- "register_mcp_tools idempotency" — exercised implicitly by e2e, no explicit double-call assertion.

### GAP-4 · Live-backend deliverables deferred — accepted scope cut

- Live MongoDB MCP e2e test (design §7.1, marked "needs Node + Atlas") and the Devpost demo script (§8.3 item 8) are not implemented. Both require the user's Atlas cluster; everything upstream is wired and verified via the stub server.

### GAP-5 · Cosmetic placement differences

- `McpServerState` lives in `bridge.py` (design sketched it in `registry.py`); `get_registrations()` is exposed at package level (`mcp.get_registrations()`) instead of `mcp.registry.get_registrations()`. Both are improvements; update design wording.

---

## 3. Act-1 Resolution (2026-06-09)

| Gap | Resolution |
|-----|------------|
| GAP-1 | **Fixed** — `build_subprocess_env()` in `llmai/mcp/client.py` merges the SDK's minimal default environment with only the config-named vars; full parent env no longer inherited. Regression test `test_parent_secrets_not_inherited` added. |
| GAP-2 | **Design updated** — §3.3 now states the OpenAI charset rule (dashes kept). |
| GAP-3 | **Fixed** — added `test_nonexistent_command_yields_failed_state` (init-level failed state) and `TestRegisterMcpToolsIdempotency` (double-registration). |
| GAP-4 | **Deferred (accepted)** — live MongoDB e2e + demo script require the user's Atlas cluster; stub-server e2e covers the protocol path. |
| GAP-5 | **Design updated** — §3.2 type placement and §4.2 call path corrected. |

Re-verification: 165 unit tests + 4 e2e pass; ruff clean. The e2e run also
confirms servers spawn correctly under the restricted environment.

## 4. Verdict

**98% ≥ 90%** → proceed to Report phase. The only open item (GAP-4) is a
documented scope cut, not a defect.
