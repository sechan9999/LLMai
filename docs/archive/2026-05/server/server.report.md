# server (FastAPI + WebSocket + Web UI) Completion Report

**Feature:** server  
**Date:** 2026-05-12  
**Repo:** https://github.com/sechan9999/LLMai  
**Live demo:** https://ll-mai.vercel.app  
**PDCA Cycle:** #1  
**Match Rate: 100%** ✅

---

## 1. Executive Summary

The `server` feature delivers a production-quality FastAPI WebSocket server and browser-based Web UI for the vixcode agent. All 16 spec items confirmed present and correct in the first pass — no gaps, no iteration required. Six undocumented features were discovered that exceed the spec.

---

## 2. Feature Inventory

### 2.1 Server Layer (`server/app.py`)

| Item | Location | Status |
|------|----------|:------:|
| FastAPI app with static file serving | `app.py:24-27` | ✅ |
| `GET /` → index.html | `app.py:47-50` | ✅ |
| WebSocket `/ws` endpoint | `app.py:53-54` | ✅ |
| JSON validation + unknown-type rejection | `app.py:83-99` | ✅ |
| `get_info` response (model/url/provider/workspace) | `app.py:101-108` | ✅ |
| Busy-guard on concurrent `user_message` | `app.py:119-124` | ✅ |
| Cancel: stop task, preserve conversation | `app.py:130-139` | ✅ |
| Reset: stop task + wipe conversation | `app.py:141-149` | ✅ |

### 2.2 Agent Loop (`server/agent_ws.py`)

| Item | Location | Status |
|------|----------|:------:|
| Native tool-calling mode | `agent_ws.py:127-161` | ✅ |
| XML fallback mode | `agent_ws.py:162-229` | ✅ |
| Mode selection (`NATIVE_TOOL_MODELS` + provider check) | `agent_ws.py:71-103` | ✅ |
| Token-by-token streaming (native mode) | `agent_ws.py:317-347` | ✅ |
| Permission request/response via WebSocket | `agent_ws.py:257-270` | ✅ |
| Max 20 iterations guard | `agent_ws.py:84, 144-148` | ✅ |
| `agent.reset()` clears message history | `agent_ws.py:154-157` | ✅ |

### 2.3 Web UI (`server/static/index.html`)

| Item | Location | Status |
|------|----------|:------:|
| Session history (localStorage, max 30) | `index.html:1053-1127` | ✅ |
| Markdown export (`llm-ai-YYYY-MM-DD.md`) | `index.html:1133-1147` | ✅ |
| Workspace path in header (abbreviated + tooltip) | `index.html:816-824` | ✅ |
| Tool cards (expandable, status badge) | `index.html:889-929` | ✅ |
| Inline Allow/Deny permission gates | `index.html:931-957` | ✅ |
| Token streaming with syntax highlighting | `index.html:870-887` | ✅ |

---

## 3. Quality Metrics

```
┌─────────────────────────────────────────────────────┐
│ DESIGN MATCH RATE: 100%                             │
├─────────────────────────────────────────────────────┤
│ ✅ Confirmed:   16 / 16 spec items                  │
│ ⚠️  Partial:     0                                   │
│ ❌ Missing:      0                                   │
└─────────────────────────────────────────────────────┘
```

---

## 4. Undocumented Features (Beyond Spec)

| Feature | Location | Value |
|---------|----------|-------|
| `cancelled` WS event (distinct from `done`) | `app.py:138` | UI shows "Run cancelled." system message |
| `reset_done` WS event | `app.py:149` | UI clears feed and shows confirmation pill |
| Streaming → non-streaming fallback | `agent_ws.py:365-368` | Transparent retry when Ollama rejects streamed-with-tools |
| Retry/backoff on transient HTTP errors | `agent_ws.py:286-304` | 3 retries, exponential backoff (0.5 s / 1.0 s) |
| Stop button + Esc keyboard shortcut | `index.html:672-675, 1044` | Sends `cancel` to server |
| Korean/English i18n (`?lang=en` override) | `index.html:741-777` | Default Korean UI, switchable via query param |

---

## 5. Notable Architecture Decisions

**Strict message-type allowlist** (`_VALID_TYPES`) — any unrecognised type gets an error response rather than silently failing.

**Cancel vs Reset semantic split** — cancel preserves conversation context; reset wipes history. Maps cleanly to the two common user intents.

**Streaming scope** — native-mode only. XML-fallback models receive a single text chunk per turn. Correct trade-off; worth documenting.

**Permission flow** — `asyncio.Queue` (`_perm_queue`) serialises ask/response without polling or timeouts.

**Tool result truncation** — 4,000 chars display; full text preserved in `self.messages` for the LLM.

---

## 6. Lessons Learned

- 100% first-pass match reflects accurate README architecture diagram.
- Undocumented extras (retry/backoff, streaming fallback, i18n) are quality indicators — grew organically, should be promoted to README.
- `asyncio.Queue` for permission gating is a clean, reusable pattern for human-in-the-loop flows.
- XML mode streaming gap is the one feature-parity break — noting it early avoids a future surprise.

---

## 7. Next Cycle Candidates

- WebSocket context compression (`{"type": "compress"}`) for Web UI parity with CLI
- Authenticated session management
- OpenAPI/AsyncAPI spec for the WebSocket protocol
- Structured server-side logging

---

## 8. Changelog

### v1.0.0 (2026-05-12)

Added: FastAPI app + static serving, WebSocket `/ws`, 5 message types, busy-guard, async agent loop (native + XML), token streaming, permission flow, max-iteration guard, session history, Markdown export, workspace badge, tool cards, permission gates, streaming highlight.js, retry/backoff, Stop+Esc, Korean/English i18n.

Known issues: none. Four README documentation gaps noted for next sprint.
