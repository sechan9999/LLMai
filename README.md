<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?style=flat-square&logo=python" />
  <img src="https://img.shields.io/badge/ollama-local%20LLM-green?style=flat-square" />
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" />
  <img src="https://img.shields.io/badge/status-alpha-orange?style=flat-square" />
  <a href="https://ll-mai.vercel.app"><img src="https://img.shields.io/badge/demo-ll--mai.vercel.app-6aa9ff?style=flat-square" /></a>
</p>

<h1 align="center">LLM ai</h1>

<p align="center">
  <strong>A local-first AI coding agent powered by Ollama</strong><br/>
  <em>Read, write, edit files and run shell commands — orchestrated by your local LLM, with explicit permission gates.</em>
</p>

---

## What is LLM ai?

**LLM ai** is a fully local, privacy-first AI coding assistant that connects to [Ollama](https://ollama.ai) to power an agentic loop. The LLM can autonomously plan, read files, write code, and execute commands to complete tasks — all without sending data to external APIs.

It ships with **two interfaces**:

| Interface | How to Run | Best For |
|-----------|-----------|----------|
| **CLI (REPL)** | `vixcode` or `python -m vixcode` | Terminal power-users |
| **Web UI** | `vixcode-server` or `python run_server.py` | Visual, browser-based interaction |

**Live demo:** [ll-mai.vercel.app](https://ll-mai.vercel.app) — connects directly to your local Ollama from the browser, no proxy.

---

## Key Features

- 🔒 **100% Local** — No API keys, no cloud. Everything runs on your machine via Ollama.
- 🤖 **Agentic Loop** — The LLM chains tool calls (read → edit → test) autonomously until the task is done.
- 🛡️ **Permission System** — Read-only ops auto-approve; writes and shell commands require explicit approval.
- 🔧 **19 Built-in Tools** — 8 core tools (`read_file`, `write_file`, `edit_file`, `run_command`, `list_files`, `search_code`, `fetch_url`, `create_directory`) + 11 GitLab tools.
- 🗂️ **Path Sandboxing** — All file operations restricted to the workspace directory.
- 🖥️ **Cross-platform** — Windows (PowerShell) and Unix shell support.
- 🌐 **Dual Interface** — Rich terminal REPL + dark-mode Web UI with session history.
- 🔄 **Dual Tool-Calling Modes** — Native OpenAI-compatible tools for supported models + XML fallback for others.
- 📦 **Context Compression** — Automatic summarisation when conversation history grows large.
- ⚡ **WebSocket Streaming** — Real-time token streaming in the Web UI.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    User Interface                     │
│  ┌─────────────────┐    ┌──────────────────────────┐ │
│  │   CLI (REPL)    │    │   Web UI (index.html)    │ │
│  │   vixcode/      │    │   server/static/         │ │
│  │   main.py       │    │   ↕ WebSocket (/ws)      │ │
│  └───────┬─────────┘    └────────┬─────────────────┘ │
│          │                       │                    │
│  ┌───────▼───────────────────────▼─────────────────┐ │
│  │         Agent Loop (20 max iterations)           │ │
│  │   vixcode/agent.py  |  server/agent_ws.py        │ │
│  └───────────────────────┬─────────────────────────┘ │
│                          │                            │
│  ┌───────────────────────▼─────────────────────────┐ │
│  │         LLM Backend (OpenAI-compat API)          │ │
│  │   Ollama localhost:11434  |  Gemini  |  custom   │ │
│  └───────────────────────┬─────────────────────────┘ │
│                          │                            │
│  ┌───────────────────────▼─────────────────────────┐ │
│  │            Tools  (vixcode/tools.py)             │ │
│  │  read_file · write_file · edit_file             │ │
│  │  run_command · list_files · search_code         │ │
│  │  fetch_url · create_directory                   │ │
│  └───────────────────────┬─────────────────────────┘ │
│                          │                            │
│  ┌───────────────────────▼─────────────────────────┐ │
│  │       Permissions  (vixcode/permissions.py)      │ │
│  │  allow: read_file, list_files, search_code      │ │
│  │  ask:   write_file, edit_file, run_command      │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

---

## Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.ai)** installed and running (`ollama serve`)
- A downloaded model — e.g. `ollama pull qwen2.5-coder` (recommended)

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/sechan9999/LLMai.git
cd LLMai
pip install -e .
```

### 2. Start Ollama

```bash
ollama serve
# Pull a model if you haven't already:
ollama pull qwen2.5-coder
```

### 3. Configure (optional)

```bash
cp config.example.json config.json
```

```json
{
  "ollama_url": "http://localhost:11434",
  "model": "qwen2.5-coder",
  "permissions": {
    "read_file":         "allow",
    "list_files":        "allow",
    "search_code":       "allow",
    "fetch_url":         "allow",
    "write_file":        "ask",
    "edit_file":         "ask",
    "run_command":       "ask",
    "create_directory":  "ask"
  }
}
```

### 4. Run

**Web UI** (recommended):
```bash
vixcode-server
# Opens at http://127.0.0.1:7777
```

**CLI:**
```bash
vixcode
```

---

## Web UI Features

The Web UI (`vixcode-server`) provides a full-featured chat interface:

| Feature | Description |
|---------|-------------|
| **Session history** | Conversations saved to browser localStorage; restore any past session from the sidebar |
| **Export** | Download the current conversation as a Markdown file |
| **Workspace path** | Current workspace directory shown in the header |
| **Tool cards** | Each tool call shown inline — expand to see full output |
| **Permission gates** | Allow/Deny buttons appear inline for write and shell operations |
| **Streaming** | Token-by-token streaming with syntax highlighting |

---

## Tools Reference

### Core Tools (always available)

| Tool | Permission | Description |
|------|-----------|-------------|
| `read_file` | allow | Read file with line numbers; supports offset/limit |
| `write_file` | ask | Write content to a file, creating parents as needed |
| `edit_file` | ask | Replace a unique string in a file |
| `run_command` | ask | Execute a shell command (dangerous patterns blocked) |
| `list_files` | allow | List directory contents with optional glob filter |
| `search_code` | allow | Search for patterns across files (regex, ripgrep-style) |
| `fetch_url` | allow | Fetch plain text from a URL (first 8 000 chars) |
| `create_directory` | ask | Create a directory and missing parents |

### GitLab Tools (when `GITLAB_TOKEN` is set)

| Tool | Use case |
|------|----------|
| `gitlab_list_issues`, `gitlab_get_issue` | Triage open bugs |
| `gitlab_create_issue`, `gitlab_comment_issue` | Create issues from findings |
| `gitlab_list_mrs`, `gitlab_get_mr` | Review open merge requests |
| `gitlab_create_mr`, `gitlab_comment_mr` | Open MRs programmatically |
| `gitlab_list_pipelines`, `gitlab_get_pipeline`, `gitlab_get_job_log` | Diagnose CI failures |

Read-only tools auto-allow; write tools (create/comment) use the normal permission prompt.

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `/reset` | Clear conversation context |
| `/model <name>` | Switch to a different model |
| `/models` | List locally available Ollama models |
| `/tokens` | Show estimated token count |
| `/perms` | Show current permission settings |
| `/compress` | Force context compression |
| `/exit` | Quit |

---

## Supported Models

### Native Tool-Calling (recommended)

| Model family | Example pull |
|---|---|
| Qwen 2.5 / 2.5-Coder / 3 | `ollama pull qwen2.5-coder` |
| Llama 3.1 / 3.2 / 3.3 | `ollama pull llama3.2` |
| Mistral NeMo / FireFunction | `ollama pull mistral-nemo` |
| Command-R / Command-R+ | `ollama pull command-r` |

### XML Fallback Mode

Models that don't support OpenAI-compatible tool calling (`gemma3`, `phi3`, `mistral`, etc.) use an XML-based format parsed from the model's text output. Performance is slightly lower but functional.

---

## Permission Modes

| Mode | Behaviour |
|------|-----------|
| `allow` | Auto-approve — used for read-only operations |
| `ask` | Show an Allow/Deny prompt before executing |
| `deny` | Always block |

---

## Cloud Backends (optional)

The agent loop speaks the OpenAI `/v1/chat/completions` contract, so it works with any compatible backend.

### Google Gemini

```bash
export GEMINI_API_KEY=your-aistudio-key
# Optional overrides:
# export GEMINI_MODEL=gemini-2.5-flash
# export GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
```

The CLI banner and Web UI header report `Provider: Google Gemini` when active. Without `GEMINI_API_KEY`, the app falls back to local Ollama.

**Vertex AI** works via the same layer — set `GEMINI_BASE_URL` to your Vertex OpenAI-compat endpoint and supply a bearer token via `GEMINI_API_KEY`.

### Custom endpoint

Set `ollama_url` in `config.json` to any OpenAI-compatible base URL (LM Studio, vLLM, etc.).

---

## GitLab Integration

```bash
export GITLAB_TOKEN=glpat-…           # personal access token, scope: api
export GITLAB_URL=https://gitlab.com  # optional, defaults to gitlab.com
export GITLAB_PROJECT=group/repo      # optional, auto-detected from git remote
```

---

## Hosted Demo (Vercel)

[ll-mai.vercel.app](https://ll-mai.vercel.app) — a tab-based interface with three views:

- **Chat** (default) — full-height chat that connects directly to your local Ollama at `localhost:11434`; prompts never leave the browser
- **About** — features, agent loop diagram, and product highlights
- **Install** — copy-ready quick-start commands

The status pill shows `Local · <model>` when Ollama is detected, or `Cloud · <provider>` when the optional cloud fallback is active. If neither is reachable, the UI links to the Install tab.

### Optional cloud fallback for your fork

1. Get a free API key at [console.groq.com](https://console.groq.com/keys).
2. Add to Vercel environment: `GROQ_API_KEY` (and optionally `GROQ_MODEL`, default `llama-3.3-70b-versatile`).
3. Redeploy. The serverless function will return `available: true` and the browser will route fallback requests there.

**Rate limiting (Upstash):** add `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN` to cap each IP at 10 req/min and the deployment at 1 000 req/day.

---

## Project Structure

```
LLMai/
├── config.example.json   # Configuration template
├── pyproject.toml        # Package metadata & dependencies
├── run_server.py         # Web UI server entry point
├── Dockerfile
├── docker-compose.yml
├── vercel.json           # Vercel deployment (outputDirectory: website)
├── .github/workflows/ci.yml
├── api/
│   └── chat.js           # Vercel serverless cloud fallback
├── server/
│   ├── app.py            # FastAPI app (routes + WebSocket)
│   ├── agent_ws.py       # Async agent loop (native + XML modes)
│   └── static/
│       └── index.html    # Web UI — session history, export, streaming
├── vixcode/
│   ├── main.py           # CLI entry point (REPL)
│   ├── agent.py          # Core sync agent loop
│   ├── llm.py            # OpenAI-compat HTTP client (Ollama / Gemini)
│   ├── tools.py          # 8 core tool definitions & implementations
│   ├── gitlab_tools.py   # 11 GitLab tools (opt-in via GITLAB_TOKEN)
│   └── permissions.py    # Permission management
├── website/
│   └── index.html        # Tab-based landing page (Chat / About / Install)
├── tests/
│   ├── test_tools.py
│   ├── test_permissions.py
│   ├── test_agent.py
│   ├── test_llm.py
│   └── test_gitlab_tools.py
└── docs/
    └── tips/             # Architecture & setup guides (Korean)
```

---

## Documentation

- [Agent Architecture](docs/tips/agent-architecture.md) — how the agentic loop works
- [Local LLM Setup](docs/tips/local-llm-setup.md) — best practices for Ollama
- [Permission System](docs/tips/permission-system.md) — configuring allow/ask/deny
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
- [highlight.js](https://highlightjs.org) — Code syntax highlighting
- [marked.js](https://marked.js.org) — Markdown rendering
