# Gap Analysis — vixcode (LLM ai)

**Feature:** vixcode  
**Date:** 2026-05-12  
**Spec:** `README.md` (de-facto design doc — no formal plan/design documents)  
**Implementation:** `vixcode/`, `server/`  
**Match Rate: 92%** ✅ (threshold: 90%)

---

## Overall Scores

| Category | Score |
|----------|:-----:|
| Core Tools (8/8) | 100% |
| GitLab Tools (11/11) | 100% |
| CLI Commands (7/7) | 100% |
| Permission Modes (3/3) | 100% |
| LLM Providers (3/3) | 100% |
| Dual Tool-Calling Modes | 100% |
| Context Compression | 90% (CLI only, not Web UI) |
| WebSocket Streaming | 100% |
| Web UI Features (6/6) | 100% |
| Path Sandboxing | 100% |
| **Overall Match Rate** | **92%** |

---

## Gaps Found (3 minor)

### GAP-1: `fetch_url` permission default — Low severity
- **README says:** `fetch_url` → `allow`  
- **Implementation:** `permissions.py DEFAULT` does not include `fetch_url`; unknown tools fall through to `ask`  
- **Fix:** Add `"fetch_url": "allow"` to `permissions.py:DEFAULT` dict

### GAP-2: CLI banner missing `/compress` — Low severity (cosmetic)
- **README says:** `/compress` — Force context compression  
- **Implementation:** `/compress` handler exists (`main.py:127`) but the startup banner string (`main.py:67`) omits it from the displayed command list  
- **Fix:** Add `/compress` to the banner help string

### GAP-3: WebSocket agent has no context compression — Medium severity
- **README says:** "Context Compression — Automatic summarisation when conversation history grows large" (top-level feature bullet)  
- **Implementation:** `vixcode/agent.py:maybe_compress` exists for CLI only; `server/agent_ws.py:WebSocketAgent` has no compression logic  
- **Options:** (a) Port `maybe_compress` to `WebSocketAgent`, or (b) clarify in README that compression is CLI-only

---

## Extra Features in Implementation (not in README)

| Feature | Location | Note |
|---------|----------|------|
| `run_bash` legacy alias | `tools.py:493` | Backward compat alias for `run_command` |
| `/quit`, `exit`, `quit` exit aliases | `main.py:97` | Only `/exit` documented |
| WebSocket `cancel` message | `app.py:130`, `index.html` | Mid-run cancellation not mentioned in README |
| Dangerous-command blocklist | `tools.py:64-80` | Blocks `rm -rf /`, fork bombs, `mkfs` — strong safety feature, undocumented |
| Retry/backoff on transient LLM errors | `llm.py:93-111`, `agent_ws.py:286-303` | Up to 3 retries with exponential backoff |

---

## Recommended Fixes

**Immediate (surgical edits, < 5 min):**
1. `permissions.py` — add `"fetch_url": "allow"` to `DEFAULT`
2. `main.py` — add `/compress` to the banner help string

**Medium-priority:**
3. Either port `maybe_compress` to `WebSocketAgent`, or add a README note scoping compression to CLI

**Documentation:**
4. Document the dangerous-command blocklist in README (it's a real selling point)
5. Document the WebSocket `cancel` UX in README's Web UI Features table

---

## Decision

Match Rate **92% ≥ 90%** — **Act/iterate phase is NOT required.**  
Recommended next step: `/pdca report vixcode`
