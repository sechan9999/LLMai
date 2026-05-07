<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?style=flat-square&logo=python" />
  <img src="https://img.shields.io/badge/ollama-local%20LLM-green?style=flat-square" />
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" />
  <img src="https://img.shields.io/badge/status-alpha-orange?style=flat-square" />
</p>

<h1 align="center">⚡ LLMai (vixcode)</h1>

<p align="center">
  <strong>A local AI coding agent powered by Ollama</strong><br/>
  <em>Read, write, edit files and run shell commands — all orchestrated by your local LLM.</em>
</p>

---

## 🎯 What is LLMai?

**LLMai** (internally named **vixcode**) is a fully local, privacy-first AI coding assistant that connects to [Ollama](https://ollama.ai) to power an agentic loop — meaning the LLM can autonomously plan, read files, write code, and execute commands to complete your tasks, all without sending data to external APIs.

It ships with **two interfaces**:

| Interface | How to Run | Best For |
|-----------|-----------|----------|
| **CLI (REPL)** | `vixcode` or `python -m vixcode` | Terminal power-users |
| **Web UI** | `vixcode-server` or `python run_server.py` | Visual, browser-based interaction |

---

## ✨ Key Features

- 🔒 **100% Local** — No API keys, no cloud. Everything runs on your machine via Ollama.
- 🤖 **Agentic Loop** — Not just chat: the LLM can chain multiple tool calls (read → edit → test) autonomously.
- 🛡️ **Permission System** — Read-only operations auto-approve; writes & shell commands require your explicit approval.
- 🔧 **6 Built-in Tools** — `read_file`, `write_file`, `edit_file`, `run_command`, `list_files`, `search_code`
- 🛡️ **Path Sandboxing** — All file operations are restricted to the workspace directory
- 🖥️ **Cross-platform** — Windows (PowerShell) and Unix shell support
- 🌐 **Dual Interface** — Rich terminal REPL (via [Rich](https://github.com/Textualize/rich)) + beautiful dark-mode Web UI
- 🔄 **Dual Tool-Calling Modes** — Native OpenAI-compatible tools for supported models (Qwen, Llama 3.x, etc.) + XML-based fallback for other models (Gemma, Phi, Mistral, etc.)
- 📦 **Context Management** — Automatic context compression when conversation gets too long
- ⚡ **WebSocket-based** — Real-time streaming communication between Web UI and server

---

## 🏗️ Architecture

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
│  │             Agent Loop (20 max iterations)       │ │
│  │  vixcode/agent.py  |  server/agent_ws.py        │ │
│  └───────────────────────┬─────────────────────────┘ │
│                          │                            │
│  ┌───────────────────────▼─────────────────────────┐ │
│  │           Ollama (localhost:11434)                │ │
│  │           /v1/chat/completions (OpenAI compat.)  │ │
│  └─────────────────────────────────────────────────┘ │
│                          │                            │
│  ┌───────────────────────▼─────────────────────────┐ │
│  │            Tools (vixcode/tools.py)              │ │
│  │  read_file · write_file · edit_file             │ │
│  │  run_bash  · list_files  · search_code          │ │
│  └─────────────────────────────────────────────────┘ │
│                          │                            │
│  ┌───────────────────────▼─────────────────────────┐ │
│  │         Permissions (vixcode/permissions.py)     │ │
│  │  allow: read_file, list_files, search_code      │ │
│  │  ask:   write_file, edit_file, run_bash         │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

---

## 📋 Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.ai)** installed and running (`ollama serve`)
- A downloaded model (e.g., `ollama pull gemma3:4b` or `ollama pull qwen2.5-coder`)

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/sechan9999/LLMai.git
cd LLMai
pip install -e .
```

### 2. Make sure Ollama is running

```bash
ollama serve
# In another terminal, pull a model:
ollama pull gemma3:4b
```

### 3. Configure (optional)

Copy the example config and customize:

```bash
cp config.example.json config.json
```

Edit `config.json` to set your preferred model and Ollama URL:

```json
{
  "ollama_url": "http://localhost:11434",
  "model": "gemma3:4b",
  "permissions": {
    "read_file":   "allow",
    "list_files":  "allow",
    "search_code": "allow",
    "write_file":  "ask",
    "edit_file":   "ask",
    "run_command": "ask"
  }
}
```

### 4. Run

**CLI mode:**
```bash
vixcode
# or
python -m vixcode
```

**Web UI mode:**
```bash
vixcode-server
# or
python run_server.py
```

The Web UI will open at `http://127.0.0.1:7777` automatically.

---

## 💻 CLI Commands

| Command | Description |
|---------|-------------|
| `/reset` | Clear conversation context |
| `/model <name>` | Switch to a different model |
| `/models` | List locally available models |
| `/tokens` | Show estimated token count |
| `/perms` | Show current permission settings |
| `/compress` | Force context compression |
| `/exit` | Quit |

---

## 📂 Project Structure

```
LLMai/
├── config.example.json  # Configuration template
├── pyproject.toml       # Package metadata & dependencies
├── requirements.txt     # Pip dependencies
├── run_server.py        # Web UI server entry point
├── LICENSE              # MIT license
├── README.md            # This file
├── .github/workflows/
│   └── ci.yml           # GitHub Actions CI
├── server/
│   ├── __init__.py
│   ├── app.py           # FastAPI app (routes + WebSocket)
│   ├── agent_ws.py      # WebSocket agent loop (async)
│   └── static/
│       └── index.html   # Web UI (single-page app, i18n)
├── tests/
│   ├── test_tools.py    # Tool & path-safety tests
│   ├── test_permissions.py
│   ├── test_agent.py    # Agent loop tests (mocked LLM)
│   └── test_llm.py      # HTTP client tests
└── vixcode/
    ├── __init__.py
    ├── main.py           # CLI entry point (REPL)
    ├── agent.py          # Core agent loop (sync)
    ├── llm.py            # Ollama client (HTTP)
    ├── tools.py          # Tool definitions & implementations
    └── permissions.py    # Permission management
```

---

## 🔧 Supported Models

### Native Tool-Calling (recommended)
Models that support OpenAI-compatible tool calling:
- `qwen2.5-coder`, `qwen2.5`, `qwen3`
- `llama3.1`, `llama3.2`, `llama3.3`
- `mistral-nemo`, `firefunction`
- `command-r`, `command-r-plus`

### XML Fallback Mode
All other models (e.g., `gemma3`, `phi3`, `mistral`) use an XML-based tool-calling format parsed from the model's text output.

---

## 🔐 Permission Modes

| Mode | Behavior |
|------|----------|
| `allow` | Auto-approve (default for read operations) |
| `ask` | Prompt user for approval (default for writes & shell) |
| `deny` | Always block |

---

## 📜 License

MIT

---

## 🙏 Acknowledgments

- [Ollama](https://ollama.ai) — Local LLM runtime
- [FastAPI](https://fastapi.tiangolo.com) — Web framework
- [Rich](https://github.com/Textualize/rich) — Terminal formatting
- [highlight.js](https://highlightjs.org) — Code syntax highlighting (Web UI)
- [marked.js](https://marked.js.org) — Markdown rendering (Web UI)
