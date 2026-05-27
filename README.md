<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?style=flat-square&logo=python" />
  <img src="https://img.shields.io/badge/ollama-local%20LLM-green?style=flat-square" />
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" />
  <img src="https://img.shields.io/badge/status-alpha-orange?style=flat-square" />
  <a href="https://ll-mai.vercel.app"><img src="https://img.shields.io/badge/demo-ll--mai.vercel.app-6aa9ff?style=flat-square" /></a>
</p>

<h1 align="center">LLMai</h1>

<p align="center">
  <strong>A local-first AI coding agent with three layers of awareness.</strong><br/>
  <em>Runs on your own Ollama. Remembers across sessions. Searches your org's knowledge before writing code. Observable end-to-end.</em>
</p>

---

## What LLMai is

A privacy-first AI coding agent that runs the model locally and gives it three distinct kinds of awareness — not just one giant chat window:

| Layer | Backed by | What it gives the agent |
|-------|-----------|-------------------------|
| **Operational** | Dynatrace (OpenTelemetry → Bindplane) | Every tool call traced: latency, token count, permission outcome, success/error |
| **Personal** | MongoDB Atlas (per-workspace) | Recalls *your* past sessions, decisions, and extracted facts. Boots warm |
| **Organizational** | Elastic (per-org) | Hybrid search over GitLab issues, CI failure logs, docs — checks "have we seen this before?" before writing code |

All three are **opt-in**. The core agent runs 100% locally with no external dependencies. Each integration is one config flip away.

**Live demo:** [ll-mai.vercel.app](https://ll-mai.vercel.app)

---

## Stack at a glance

```
                                        ┌─ search_knowledge ──► Elastic (issues + docs)
                                        │
   Browser / CLI ──► Agent Loop ────────┼─ recall_memory ─────► MongoDB Atlas
                          │             │                       (per-workspace sessions
                          │             │                        + summaries + knowledge)
                          │             │
                          │             └─ query_logs ────────► Elastic ES|QL
                          │                                     (pipeline + agent self-logs)
                          │
                          ▼
                     OTel spans
                          │
                          ▼
                  Bindplane ──┬──► Dynatrace (traces + metrics)
                              │
                              └──► Elastic llmai-agent-logs
                                   (so the agent can query itself)

LLM backend: Ollama localhost:11434 — Gemini / Groq optional
```

---

## Two interfaces

| | How to run | Best for |
|---|---|---|
| **CLI REPL** | `llmai` | Terminal power users |
| **Web UI** | `llmai-server` → http://localhost:7777 | Browser, streaming, permission cards |

---

## Quick start (core only, no partner integrations)

Install from PyPI (the distribution is named `llmai-agent` because bare
`llmai` was already taken; the import path is still `import llmai`):

```bash
pip install llmai-agent
ollama serve
ollama pull qwen2.5-coder
llmai-server   # opens http://localhost:7777
```

Or install from source for development:

```bash
git clone https://github.com/sechan9999/LLMai.git
cd LLMai
pip install -e .

ollama serve
ollama pull qwen2.5-coder

llmai-server   # opens http://localhost:7777
```

That's it. The agent has 8 core tools (read/write/edit files, run shell, search code, list files, fetch URL, mkdir) plus 11 GitLab tools when `GITLAB_TOKEN` is set. Read-only ops auto-approve; writes and shell commands prompt for permission.

---

## Adding the three layers (10-15 min each)

### 1. Dynatrace — observe every tool call

```bash
make install-telemetry          # adds opentelemetry packages

# in .env (copy from .env.example):
DT_ENDPOINT=https://<your>.live.dynatrace.com
DT_API_TOKEN=dt0c01.YOUR_TOKEN

make bindplane-up               # starts the OTel collector locally

export LLMAI_OTEL_ENABLED=true
export LLMAI_OTEL_ENDPOINT=http://localhost:4318
llmai-server
```

Spans: `agent.turn` → `agent.iteration` → `llm.chat` + `tool.invocation`. Metrics: tool invocation counts, LLM latency, token histograms.

Full guide: **[docs/dynatrace-setup.md](docs/dynatrace-setup.md)**

### 2. MongoDB Atlas — remember across sessions

```bash
make install-memory             # adds pymongo
ollama pull nomic-embed-text    # embedding model

# in config.json or env:
LLMAI_MEMORY_ENABLED=true
LLMAI_MEMORY_URI=mongodb+srv://USER:PASS@cluster.mongodb.net/

python scripts/setup_atlas_indexes.py   # one-time vector index bootstrap
llmai-server
```

Three collections: `sessions`, `summaries` (vector-embedded), `knowledge` (extracted facts, vector-embedded). New tool: `recall_memory` for the agent. On each new session, the 3 most recent prior summaries are auto-injected as a system message.

Full guide: **[docs/atlas-setup.md](docs/atlas-setup.md)**

### 3. Elastic — search org knowledge before writing code

```bash
make install-elastic            # adds elasticsearch client
make elastic-up                 # local ES + Kibana via docker
make elastic-setup              # creates llmai-* indices

# optional: pull org knowledge in
export GITLAB_TOKEN=glpat-...
export GITLAB_PROJECT=group/project
make elastic-ingest             # pulls last 500 issues + 50 failed pipelines

export LLMAI_ELASTIC_ENABLED=true
export LLMAI_ELASTIC_URL=http://localhost:9200
llmai-server
```

Two tools: `search_knowledge` (hybrid keyword + dense vector, RRF-fused, auto-approved) and `query_logs` (raw ES|QL, permission-gated). System prompt nudges the model to call `search_knowledge` before writing code that touches error paths or external APIs.

Full guide: **[docs/elastic-setup.md](docs/elastic-setup.md)**

### One-command demo bootstrap

```bash
make demo-up           # starts Elastic + Kibana + Bindplane
make demo-bootstrap    # pulls embed model + creates ES indices
make demo-status       # health check across the whole stack
```

---

## Key features

- **100% local by default** — no API keys, no cloud, nothing leaves your machine
- **Agentic loop** — observe → judge → act, up to 20 iterations per turn
- **Permission gates** — read-only auto-approves; writes and shell prompt
- **Three-layer awareness** — operational (Dynatrace), personal (Atlas), org (Elastic) — all opt-in
- **MCP-compatible tool shapes** — `recall_memory`, `search_knowledge`, `query_logs` mirror the official MCP server contracts
- **Dual tool-calling modes** — native OpenAI function calling for capable models; XML fallback for `gemma3`, `phi3`, etc.
- **Context compression** — auto-summarizes when conversation exceeds ~50k tokens
- **Workspace sandboxing** — file ops restricted to `WORKSPACE_ROOT`; dangerous command patterns blocked
- **Provider-agnostic** — Ollama, Gemini, Groq (cloud fallback for the hosted demo)
- **Dual interface** — CLI REPL + WebSocket-streaming Web UI

---

## Tools (when their layer is enabled)

| Category | Tools | Default permission |
|----------|-------|-------------------|
| Core (8) | `read_file`, `write_file`, `edit_file`, `run_command`, `list_files`, `search_code`, `fetch_url`, `create_directory` | reads `allow`, writes/shell `ask` |
| GitLab (11) | `gitlab_list_issues`, `gitlab_get_mr`, `gitlab_get_job_log`, … | reads `allow`, mutations `ask` |
| Memory (1) | `recall_memory` | `allow` |
| Elastic (2) | `search_knowledge`, `query_logs` | `allow` / `ask` |

Tools are registered conditionally — the model never sees a tool whose backend isn't connected.

---

## Configuration

`config.json` (or env vars — env always wins):

```json
{
  "ollama_url": "http://localhost:11434",
  "model": "qwen2.5-coder",
  "permissions": { ... },
  "telemetry": { "enabled": false, "endpoint": "http://localhost:4318", ... },
  "memory":    { "enabled": false, "uri": "mongodb+srv://...", ... },
  "elastic":   { "enabled": false, "url": "http://localhost:9200", ... }
}
```

Full example: [config.example.json](config.example.json).

---

## CLI commands

| Command | Description |
|---------|-------------|
| `/reset` | Clear conversation context (and finalize session memory) |
| `/model <name>` | Switch model |
| `/models` | List Ollama models locally |
| `/tokens` | Show estimated token count |
| `/perms` | Show current permission settings |
| `/compress` | Force context compression now |
| `/exit` | Quit |

---

## Supported models

**Native tool calling** (recommended): Qwen 2.5 / 2.5-Coder / 3, Llama 3.1+, Mistral NeMo, FireFunction, Command-R(+).

**XML fallback**: gemma3, phi3, mistral — anything OpenAI-incompatible. Slightly lower fidelity but functional.

---

## Cloud backends (optional)

The agent speaks the OpenAI `/v1/chat/completions` contract.

```bash
# Gemini (via AI Studio key — also works for Vertex AI compat endpoint)
export GEMINI_API_KEY=...

# Any OpenAI-compat endpoint (LM Studio, vLLM, custom):
# set "ollama_url" in config.json
```

---

## Project structure

```
LLMai/
├── llmai/                # Python package (formerly vixcode)
│   ├── agent.py          # Sync CLI agent loop
│   ├── main.py           # CLI REPL entry point
│   ├── llm.py            # OpenAI-compat HTTP client
│   ├── tools.py          # 8 core tools + conditional registration
│   ├── gitlab_tools.py   # 11 GitLab tools
│   ├── permissions.py    # allow / ask / deny system
│   ├── telemetry.py      # OpenTelemetry init + span context managers
│   ├── memory/           # MongoDB Atlas persistent memory
│   │   ├── store.py
│   │   ├── embeddings.py
│   │   └── recall_tool.py
│   └── elastic/          # Elasticsearch knowledge search + log analytics
│       ├── client.py
│       ├── search_tool.py
│       └── query_tool.py
├── server/               # FastAPI + WebSocket Web UI
│   ├── app.py
│   ├── agent_ws.py       # Async agent loop (native + XML modes)
│   └── static/index.html
├── website/              # Landing page (Vercel)
│   └── index.html
├── api/chat.js           # Vercel serverless cloud fallback (Groq)
├── scripts/              # Bootstrap scripts for partner integrations
│   ├── setup_atlas_indexes.py
│   ├── elastic_setup_indexes.py
│   ├── elastic_ingest_gitlab.py
│   └── elastic_ingest_logs.py
├── bindplane/config.yaml             # OTel collector → Dynatrace + Elastic
├── docker-compose.bindplane.yml      # Bindplane container
├── docker-compose.elastic.yml        # Elasticsearch + Kibana
├── Makefile                          # Common dev / demo tasks
├── docs/
│   ├── dynatrace-setup.md
│   ├── atlas-setup.md
│   └── elastic-setup.md
└── tests/                # 103 passing
```

---

## Documentation

- **[Dynatrace observability](docs/dynatrace-setup.md)** — OpenTelemetry spans, metrics, Bindplane pipeline
- **[MongoDB Atlas memory](docs/atlas-setup.md)** — cross-session continuity, semantic recall
- **[Elastic knowledge search](docs/elastic-setup.md)** — hybrid search, ES|QL, agent self-logs
- [Local LLM Setup](docs/tips/local-llm-setup.md) — best practices for Ollama
- [Permission System](docs/tips/permission-system.md) — allow/ask/deny configuration
- [Tool System](docs/tips/tool-system.md) — tool definitions and sandboxing
- [OSS Comparison](docs/tips/oss-comparison.md) — vs. Claude Code, Aider, Open Interpreter, Goose

---

## License

MIT

---

## Acknowledgments

- [Ollama](https://ollama.ai) — Local LLM runtime
- [FastAPI](https://fastapi.tiangolo.com) — Web framework
- [Rich](https://github.com/Textualize/rich) — Terminal formatting
- [OpenTelemetry](https://opentelemetry.io) — Observability standard
- [Bindplane](https://bindplane.com) — OTel collector
- [Dynatrace](https://dynatrace.com), [MongoDB Atlas](https://www.mongodb.com/atlas), [Elastic](https://www.elastic.co) — Hackathon partner backends
