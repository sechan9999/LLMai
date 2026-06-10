# Gap Analysis — server (FastAPI + WebSocket + Web UI)

**Feature:** server  
**Date:** 2026-05-12  
**Spec:** `README.md` — Web UI features and architecture sections  
**Implementation:** `server/app.py`, `server/agent_ws.py`, `server/static/index.html`  
**Match Rate: 100%** ✅ (threshold: 90%)

---

## Overall Scores

| Category | Score |
|----------|:-----:|
| FastAPI routes & static serving | 100% |
| WebSocket message types (5/5) | 100% |
| Cancel / Reset semantics | 100% |
| Native + XML tool-calling modes | 100% |
| Token streaming | 100% |
| Permission request/response flow | 100% |
| Max iterations guard | 100% |
| Web UI — Session history | 100% |
| Web UI — Markdown export | 100% |
| Web UI — Workspace path in header | 100% |
| Web UI — Tool cards (expandable) | 100% |
| Web UI — Permission gates | 100% |
| Web UI — Streaming render | 100% |
| **Overall Match Rate** | **100%** |

---

## All 16 Spec Items Confirmed

| # | Spec item | Verified at | Notes |
|---|-----------|-------------|-------|
| 1 | FastAPI serves `/` + mounts `/static` | `app.py:27, 47-50` | |
| 2 | WebSocket endpoint `/ws` | `app.py:53-54` | |
| 3 | All 5 message types handled + invalid type rejected | `app.py:30, 83-99, 101-149` | Also rejects invalid JSON |
| 4 | `get_info` returns model, url, provider, workspace | `app.py:101-108` | Key name is `ollama` regardless of provider |
| 5 | Busy-guard rejects `user_message` while task running | `app.py:119-124` | |
| 6 | Cancel stops task without wiping conversation history | `app.py:130-139` | Emits `cancelled` + `done` |
| 7 | Reset stops task AND wipes history | `app.py:141-149`, `agent_ws.py:154-157` | |
| 8 | Native + XML modes both implemented | `agent_ws.py:103, 127-139, 161-229` | `_supports_native_tools()` selects mode; cloud providers always native |
| 9 | Token-by-token streaming | `agent_ws.py:317-347` | **Native mode only** — XML mode emits single chunk per turn |
| 10 | Permission request/response flow | `agent_ws.py:257-270`, `app.py:127-128` | `permission_request` WS event → user Allow/Deny → `_perm_queue` |
| 11 | Max 20 iterations guard | `agent_ws.py:84, 125, 144-148` | `MAX_ITERATIONS = 20` |
| 12 | Session history via localStorage | `index.html:1053-1127` | `SESSIONS_KEY`, capped at 30 sessions |
| 13 | Markdown export | `index.html:1133-1147` | `llm-ai-YYYY-MM-DD.md` |
| 14 | Workspace path in header | `index.html:668, 816-824` | Abbreviated (last 2 segments), full path in tooltip |
| 15 | Tool cards (expandable) | `index.html:889-929` | Click toggles `.open`, shows args + output |
| 16 | Inline permission gates | `index.html:931-957` | Allow/Deny buttons replaced with confirmation indicator after click |

---

## Extra Features (not in README)

| Feature | Location | Note |
|---------|----------|------|
| `cancelled` + `reset_done` WS events | `app.py:138, 149` | README doesn't enumerate server→client event types |
| Streaming fallback to non-streaming | `agent_ws.py:365-368` | Transparent retry when Ollama rejects streamed-with-tools |
| Retry/backoff on transient HTTP failures | `agent_ws.py:286-304` | 3 retries, exponential backoff (0.5s, 1.0s) |
| Stop button + Esc shortcut | `index.html:672-675, 1044-1046` | UX layer on top of `cancel` |
| Korean/English i18n (`?lang=`) | `index.html:741-777` | Default Korean, switchable via query param |
| Tool result truncation (4000 chars display) | `agent_ws.py:255` | Full text preserved for LLM |

---

## Decision

Match Rate **100%** — **Act/iterate phase is NOT required.**
