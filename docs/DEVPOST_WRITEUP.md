## LLMai: A local-first AI coding agent with three layers of awareness

## Inspiration
Cloud-based AI coding tools send your proprietary source code, prompts, and terminal history to external servers you don't control. For privacy-conscious developers and enterprise environments, this is an unacceptable risk. But the existing "local agent" alternatives all share the same two blind spots: they forget what they did yesterday, and they ignore what your team has already learned. Your past decisions vanish at `/reset`, and the fix to the bug you're chasing is sitting in a GitLab issue your colleague filed six months ago that the model never reads.

LLMai is our answer: a 100% local AI coding agent that runs the model on your machine, then adds three opt-in "layers of awareness" so it can observe itself, remember across sessions, and search your organization's knowledge before writing code.

## What it does
LLMai doesn't just chat — it plans, reads files, writes code, and runs shell commands driven by a model on your own hardware. On top of the local agent loop, it integrates three hackathon partner backends to give the agent three distinct kinds of awareness:

-**Operational awareness via Dynatrace.** Every tool invocation is an OpenTelemetry span: `agent.turn` → `agent.iteration` → `llm.chat` + `tool.invocation`. Spans carry token counts, exec latency, permission outcome (allow / ask_allow / ask_deny / deny), and success/error — but never file contents or raw prompts. Routed via a Bindplane OTel collector so the agent never speaks Dynatrace's protocol directly.

-**Personal awareness via MongoDB Atlas.** Three collections — `sessions` (raw transcripts), `summaries` (LLM-summarized, vector-embedded), and `knowledge` (3–5 extracted facts per session, vector-embedded) — give the agent persistent memory scoped per workspace via `sha256(abs_path)[:16]`. On every new session in the same workspace, the top-3 recent summaries are auto-injected as a system message. The agent boots warm. A `recall_memory` tool gives it semantic recall on demand.

-**Organizational awareness via Elastic.** GitLab issues and project docs are ingested with dense vector embeddings; pipeline failure logs are indexed with regex-extracted `error_signature` for ES|QL. The agent gets two tools: `search_knowledge` (hybrid BM25 + kNN, RRF where available with kNN-only fallback on basic license — auto-approved) and `query_logs` (raw ES|QL, permission-gated). The system prompt nudges the model to call `search_knowledge` before writing code that touches an error path.

Plus the base agent capabilities that make all three useful:

-**Real agentic loop.** Plan the next step, call a tool, observe the result, iterate up to 20 times until the task is done.

-**Explicit-permission writes.** Read-only tools execute instantly. Anything that mutates state (writing files, running commands) pauses for your explicit approval.

-**GitLab integration.** Triage issues, fetch merge requests, read failing pipeline logs, open fix MRs — all from the agent.

-**Real MCP client over stdio.** LLMai now launches partner MCP servers as local subprocesses, discovers their tools at startup, and registers them as `mcp__{server}__{tool}` behind the same permission system as built-in tools.

Every partner integration is opt-in. The default mode is fully local with zero external calls.

## How we built it
-**Backend:** A lightweight, highly readable Python loop — no heavy abstraction frameworks. FastAPI for the Web UI, a sync REPL for the CLI, both sharing the same tool definitions and permission system.

-**AI orchestration:** Native function-calling for models like Qwen 2.5 Coder and Llama 3.1 / 3.2, with an intelligent XML-based fallback for Gemma, Phi, and Mistral.

-**Frontend:** A dark-mode full-screen browser UI (HTML / Vanilla JS / CSS) connecting via WebSockets, with real-time token streaming and inline permission cards. A rich terminal REPL for CLI users.

-**LLM engine:** Powered entirely by local Ollama instances (provider-agnostic architecture also supports Gemini and Groq fallbacks for the hosted demo).

-**Observability (Layer 1):** OpenTelemetry SDK directly in both agent loops, exporting OTLP/HTTP to a bundled Bindplane Agent (Docker container) that fans out to Dynatrace and — optionally — to Elastic for the "agent queries its own behavior" loop.

-**Memory (Layer 2):** MongoDB Atlas with Vector Search (768-dim cosine), embeddings via Ollama's `nomic-embed-text` running locally so no embedding traffic leaves the box. A bootstrap script (`scripts/setup_atlas_indexes.py`) handles vector-index creation idempotently.

-**Knowledge (Layer 3):** Elasticsearch 8.x with three indices (issues, logs, docs) plus a tee'd agent self-log index. Hybrid search via RRF retriever on Atlas / Cloud, falling back to kNN-only on basic-license clusters. Two bootstrap scripts pull GitLab issues and pipeline failures into the cluster with stable doc IDs so re-runs upsert.

## Challenges we ran into
-**Model compatibility.** Different local models handle tool-calling differently. We built a dynamic system that detects a model's capability and seamlessly switches between native JSON function calling and an XML-based fallback.

-**Context window management.** Long agentic sessions quickly fill local model context windows. We implemented a context compression engine that auto-summarizes older turns when the conversation exceeds ~50k tokens. Those compressed summaries also become the unit of cross-session recall in Atlas.

-**Security & sandboxing.** Powerful enough to run shell commands without being dangerous. Strict path-traversal blocks, a destructive-command blocklist, and a visual human-in-the-loop approval system. Telemetry never carries raw prompts or file contents — only metadata (lengths, latencies, outcomes).

-**Privacy preservation under integration.** Adding cloud-connected partners while keeping "local-first" honest meant making every layer opt-in via an env var that defaults to false, and proving that disabling the optional dependency leaves the agent functionally unchanged. We unit-tested the graceful-degradation path for each of the 4 failure modes per layer (off, package missing, bad credentials, backend unreachable).

-**Real live-demo bugs surfaced by integration testing.** Two we caught and fixed during this hackathon: (1) the `elasticsearch` Python client v9 sends `compatible-with=9` headers that Elasticsearch 8.x rejects with HTTP 400 — pinned `<9`; (2) Elasticsearch's RRF retriever requires a Platinum license, but the Docker single-node ships basic — restructured `hybrid_search` to cascade RRF → kNN-only → BM25-only, each fallback a debug-level log so it doesn't spam in steady state on Atlas / Elastic Cloud.

-**Asynchronous memory writes.** The async WebSocket agent loop couldn't block on MongoDB writes between turns, but the sync CLI loop needed deterministic save-after-turn semantics. We unified both by routing the synchronous pymongo calls through `loop.run_in_executor` in the async path, so neither loop's surface area changes.

## Accomplishments that we're proud of
-**Three layers, one agent, zero API keys required.** A fully functional local AI agent that delivers operational, personal, and organizational awareness without ever forcing a cloud dependency. The core loop runs entirely on Ollama; partner layers are pure additions, not replacements.

-**Verified semantic recall.** End-to-end tested against a real Elasticsearch cluster: `search_knowledge("chat endpoint throttling")` returns the pre-seeded rate-limit issue at score 0.84 — a pure semantic match with zero keyword overlap. `search_knowledge("cookie token rotation")` returns the auth design doc at 0.87. The agent is genuinely finding the right prior work, not pattern-matching tokens.

-**Three integrations × four failure modes × graceful degradation everywhere.** 103 unit tests pass; each partner integration was hand-verified to fail cleanly when the backend is off, when the optional dependency is missing, when credentials are wrong, and when the cluster is unreachable. The agent loop never raises into the user's turn because of a partner outage.

-**MCP requirement genuinely met.** We implemented a real MCP client layer and validated partner-server wiring over stdio, so this is no longer a contract-only shim.

-**A modern dark-mode dashboard** that makes it incredibly easy to monitor the agent's thought process and approve or reject state-mutating actions, with token-by-token streaming and per-turn telemetry.

## What we learned
You don't need massive, opaque frameworks to build powerful AI agents. A well-designed, permission-gated Python loop paired with the right local model (like Qwen 2.5 Coder) reaches production-level coding assistance with zero privacy trade-offs.

We also learned that the most valuable partner integration patterns aren't the obvious "send everything to the cloud" ones — they're the ones where the agent's local execution is *enriched* by cloud-side awareness: traces of its own behavior, recall of its own past work, and search over its team's existing knowledge. Each layer pays for itself in observability or capability. None of them require relocating the model.

Finally, we learned that **graceful degradation is the price of admission for opt-in features.** Every layer's failure modes had to be designed before its happy path was wired, or the agent would inherit the reliability profile of its weakest dependency. We treat telemetry, memory, and knowledge backends as nice-to-haves the agent never *needs* — and that discipline is what makes them safe to integrate.

## What's next for LLMai
-**Expand MCP coverage.** Add more partner MCP servers and harden production ergonomics (server health surfacing, reconnect diagnostics, and per-tool allowlists).

-**Continuous ingest pipelines.** Today the GitLab → Elastic ingest is a one-shot script. Move to Elastic Agent or Logstash for streaming ingest so the agent's organizational awareness stays current without manual refresh.

-**Cross-workspace recall mode.** Memory is strictly per-workspace today. Add an opt-in flag so the agent can search across all your workspaces when explicitly asked ("have I ever seen this error in any of my projects?").

-**Auto-route compute.** Use cheap models for tool selection and larger models only for code generation. Cut local-LLM cost (in time and energy) without changing the agent loop.

-**Expand native Git platform integrations beyond GitLab** (GitHub, Bitbucket) and **add Claude / OpenAI cloud paths** alongside the existing Gemini and Groq fallbacks.

-**Persistent localStorage chat history in the Web UI** so a browser refresh doesn't lose your in-progress turn.
