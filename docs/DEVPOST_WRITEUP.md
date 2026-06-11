## LLMai: A local-first AI coding agent with three layers of awareness

## Inspiration
Cloud-based AI coding tools send your proprietary source code, prompts, and terminal history to external servers you don't control. For privacy-conscious developers and enterprise environments, this is an unacceptable risk. But the existing "local agent" alternatives all share the same two blind spots: they forget what they did yesterday, and they ignore what your team has already learned. Your past decisions vanish at `/reset`, and the fix to the bug you're chasing is sitting in a GitLab issue your colleague filed six months ago that the model never reads.

LLMai is our answer: a local-first AI coding agent that runs on Ollama by default and offers a separate Gemini 3 profile built with Google's Agent Development Kit (ADK). It adds three opt-in "layers of awareness" so the agent can observe itself, remember across sessions, and search organizational knowledge before proposing code changes.

## What it does
LLMai doesn't just chat — it plans, reads files, writes code, and runs shell commands driven by a model on your own hardware. On top of the local agent loop, it integrates three hackathon partner backends to give the agent three distinct kinds of awareness:

## How LLMai fits the GitLab Partner Track

LLMai includes an executable Google ADK profile in which a configurable Gemini 3 model orchestrates read-only investigation across a local code workspace and GitLab. The profile attaches GitLab's official hosted MCP endpoint through `mcp-remote`, so the tools available to Gemini are discovered from the authenticated GitLab account rather than simulated in the application. This supports multi-step work such as reading an issue, finding related merge requests or pipeline context, inspecting the corresponding local files, and producing a grounded patch plan. The adapter omits local write and shell tools and filters GitLab tool names associated with mutations. LLMai's separate native CLI/Web runtime implements interactive approval for writes, but this submission does not claim that approval UI is part of the Google ADK profile or that the ADK agent is already deployed to Vertex AI Agent Engine.

-**Operational awareness via Dynatrace.** Every tool invocation is an OpenTelemetry span: `agent.turn` → `agent.iteration` → `llm.chat` + `tool.invocation`. Spans carry token counts, exec latency, permission outcome (allow / ask_allow / ask_deny / deny), and success/error — but never file contents or raw prompts. Routed via a Bindplane OTel collector so the agent never speaks Dynatrace's protocol directly.

-**Personal awareness via MongoDB Atlas.** Three collections — `sessions` (metadata-only by default), `summaries` (LLM-summarized, vector-embedded), and `knowledge` (3–5 extracted facts per session, vector-embedded) — give the agent persistent memory scoped per workspace via `sha256(abs_path)[:16]`. Full transcript retention is explicit opt-in. On every new session in the same workspace, the top-3 recent summaries are auto-injected as a system message. The agent boots warm. A `recall_memory` tool gives it semantic recall on demand.

-**Organizational awareness via Elastic.** GitLab issues and project docs are ingested with dense vector embeddings; pipeline failure logs are indexed with regex-extracted `error_signature` for ES|QL. The agent gets two tools: `search_knowledge` (hybrid BM25 + kNN, RRF where available with kNN-only fallback on basic license — auto-approved) and `query_logs` (raw ES|QL, permission-gated). The system prompt nudges the model to call `search_knowledge` before writing code that touches an error path.

Plus the base agent capabilities that make all three useful:

-**Real agentic loop.** Plan the next step, call a tool, observe the result, iterate up to 20 times until the task is done.

-**Explicit-permission writes.** Read-only tools execute instantly. Anything that mutates state (writing files, running commands) pauses for your explicit approval.

-**GitLab integration — via GitLab's MCP server.** Both LLMai's native MCP client and the Google ADK profile are configured to connect to GitLab's official MCP server (`https://gitlab.com/api/v4/mcp`, bridged to stdio with `mcp-remote`). They discover the tools exposed to the authenticated GitLab account at startup. The ADK profile filters state-changing tool names and is limited to investigation workflows. A built-in REST toolset (11 tools) remains available to the native runtime as a fallback for self-managed instances.

-**Real MCP client over stdio.** LLMai launches partner MCP servers as local subprocesses, discovers their tools at startup, and registers them as `mcp__{server}__{tool}` behind the same permission system as built-in tools — every remote tool defaults to ask-before-run, and server subprocesses receive only a minimal environment (no inherited secrets).

-**Daily briefing dashboard.** The local server doubles as a morning dashboard: a data-science interview question generated and answered by the local Ollama model (topic rotates daily across 8 areas), Korea headlines, US market news (Yahoo Finance RSS with a MarketWatch fallback), and CEPR's live AI Bubble Monitor charts. It auto-regenerates in the background whenever the server boots on a new day, and the hosted site embeds it directly in a ☀️ Briefing tab.

Every partner integration is opt-in. The default mode is fully local with zero external calls.

## How we built it
-**Backend:** A lightweight, highly readable Python loop — no heavy abstraction frameworks. FastAPI for the Web UI, a sync REPL for the CLI, both sharing the same tool definitions and permission system.

-**AI orchestration:** The default CLI/Web runtime uses LLMai's compact function-calling loop. The optional `google_agent` entry point is constructed by Google ADK with a configurable Gemini 3 model, read-only workspace functions, and GitLab's MCP toolset.

-**Frontend:** A dark-mode full-screen browser UI (HTML / Vanilla JS / CSS) connecting via WebSockets, with real-time token streaming and inline permission cards. A rich terminal REPL for CLI users.

-**Daily briefing:** A FastAPI startup task compares the saved dashboard's date to today and rebuilds it in the background when stale — one local LLM call for the interview Q&A, dependency-free RSS parsing for news, and a static HTML file on disk so serving it is free. The hosted site's Briefing tab health-checks the local server and iframes the dashboard through narrowly-scoped CORS: only `/healthz` and `/briefing*` are exposed to the site's origin, while the WebSocket-token endpoint stays same-origin.

-**LLM engine:** Ollama is the private-by-default backend. Setting `GEMINI_API_KEY` runs the native LLMai loop against Gemini's OpenAI-compatible API. Running `adk web .` uses the separate Google ADK profile with `gemini-3.1-pro-preview` as its default model identifier; actual access depends on the configured Google project or API account.

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
-**Local-first operation remains intact.** The default core loop still runs on Ollama without an API key. Gemini, Google ADK, GitLab MCP, and the awareness layers are explicit optional modes rather than hidden network dependencies.

-**Verified semantic recall.** End-to-end tested against a real Elasticsearch cluster: `search_knowledge("chat endpoint throttling")` returns the pre-seeded rate-limit issue at score 0.84 — a pure semantic match with zero keyword overlap. `search_knowledge("cookie token rotation")` returns the auth design doc at 0.87. The agent is genuinely finding the right prior work, not pattern-matching tokens.

-**Three integrations × four failure modes × graceful degradation everywhere.** 181 offline unit tests pass; the native partner integrations are tested to fail cleanly when disabled or unavailable. Live Google ADK and hosted GitLab MCP operation still depends on valid credentials and account eligibility.

-**Executable Google ADK and MCP wiring.** The repository contains an importable ADK `root_agent` that selects a Gemini 3 model and constructs GitLab's official MCP toolset over `mcp-remote`. Offline tests verify the selected model family, official endpoint, and read-only filter. A live demo still requires valid Google and GitLab credentials.

-**A modern dark-mode dashboard** that makes it incredibly easy to monitor the agent's thought process and approve or reject state-mutating actions, with token-by-token streaming and per-turn telemetry.

## What we learned
You do not need to abandon local execution to add a cloud orchestration option. LLMai keeps its permission-gated local runtime while providing a narrow Google ADK profile for Gemini and GitLab-assisted investigation.

We also learned that the most valuable partner integration patterns aren't the obvious "send everything to the cloud" ones — they're the ones where the agent's local execution is *enriched* by cloud-side awareness: traces of its own behavior, recall of its own past work, and search over its team's existing knowledge. Each layer pays for itself in observability or capability. None of them require relocating the model.

Finally, we learned that **graceful degradation is the price of admission for opt-in features.** Every layer's failure modes had to be designed before its happy path was wired, or the agent would inherit the reliability profile of its weakest dependency. We treat telemetry, memory, and knowledge backends as nice-to-haves the agent never *needs* — and that discipline is what makes them safe to integrate.

## What's next for LLMai
-**Expand MCP coverage.** Add more partner MCP servers and harden production ergonomics (server health surfacing, reconnect diagnostics, and per-tool allowlists).

-**Continuous ingest pipelines.** Today the GitLab → Elastic ingest is a one-shot script. Move to Elastic Agent or Logstash for streaming ingest so the agent's organizational awareness stays current without manual refresh.

-**Cross-workspace recall mode.** Memory is strictly per-workspace today. Add an opt-in flag so the agent can search across all your workspaces when explicitly asked ("have I ever seen this error in any of my projects?").

-**Auto-route compute.** Use cheap models for tool selection and larger models only for code generation. Cut local-LLM cost (in time and energy) without changing the agent loop.

-**Complete an Agent Engine deployment.** The repository demonstrates local ADK execution but does not yet claim a deployed Vertex AI Agent Engine instance. A production deployment also needs a non-interactive GitLab authentication design and cloud-native approval checkpoints.

-**Optional encrypted local history** so users can choose persistence without leaving plaintext transcripts in browser storage.
