# MongoDB Atlas persistent memory for llmai

llmai can persist its conversation history and extracted knowledge into
MongoDB Atlas, then recall it across sessions. Three collections, three
purposes:

| Collection | What | When written | When read |
|------------|------|--------------|-----------|
| `sessions` | Raw transcript per session | After every turn | On demand (by `session_id`) |
| `summaries` | LLM-summarized session, vector-embedded | At session end + on context compression | At each new session start (top 3 most recent) and via `recall_memory` |
| `knowledge` | Extracted facts/decisions, vector-embedded | At session end (3–5 per session) | Via the `recall_memory` tool the agent can call |

Per-workspace scoping uses `sha256(absolute_workspace_path)[:16]` so
memory is isolated per project but survives directory renames as long as
the resolved abs path matches.

## What the agent gains

- **Cross-session continuity** — when you reopen llmai in the same
  workspace, the top 3 most recent session summaries are auto-injected as
  a system message: *"Last time you decided X, touched files Y/Z, left
  open Q."*
- **Semantic recall** — the model can call `recall_memory("rate limit
  bug in /api/chat")` and get ranked hits from any prior session. The
  tool is read-only and auto-approved.
- **Compatible with the MongoDB Atlas MCP Server contract** — the
  `recall_memory` tool shape mirrors what the MCP server exposes, so
  swapping to a real MCP setup later is a one-file change.

## Setup (≈10 minutes)

### 1. Install the optional dep

```powershell
pip install -e ".[memory]"
```

### 2. Create an Atlas cluster (free tier works)

1. Sign up at [cloud.mongodb.com](https://cloud.mongodb.com)
2. Create a free **M0 Sandbox** cluster
3. **Database Access → Add User** — create a user, save the password
4. **Network Access → Add IP** — your current IP (or `0.0.0.0/0` for the
   demo, **not** for prod)
5. **Connect → Drivers → Python** — copy the connection string. It
   looks like `mongodb+srv://USER:PASS@cluster123.abcde.mongodb.net/`

### 3. Create the vector indexes

```powershell
$env:LLMAI_MEMORY_URI = "mongodb+srv://USER:PASS@cluster123.abcde.mongodb.net/?retryWrites=true"
python scripts/setup_atlas_indexes.py
```

Expected output:

```
  + created collection: sessions
  + created collection: summaries
  + created collection: knowledge
  + created vector index: summaries_vector on summaries
  + created vector index: knowledge_vector on knowledge
```

Atlas takes ~1–2 minutes to build the indexes. Confirm in the Atlas UI:
**Database → llmai → Search → Vector Search**, status should be `READY`.

> **Self-hosted MongoDB?** Vector Search is Atlas-only. The script will
> error with `command createSearchIndex not found`. You can still use
> llmai memory — it falls back to lexical search on the most-recent
> docs when vector search is unavailable.

### 4. Pull the embedding model

```powershell
ollama pull nomic-embed-text
```

(768 dim, ~270 MB. If you skip this step, records will still save but
won't be vector-searchable — just recoverable by session/workspace.)

### 5. Enable memory in llmai

Either env vars:

```powershell
$env:LLMAI_MEMORY_ENABLED = "true"
$env:LLMAI_MEMORY_URI     = "mongodb+srv://USER:PASS@cluster.../"
$env:LLMAI_MEMORY_DB      = "llmai"
llmai-server
```

… or `config.json`:

```json
{
  "memory": {
    "enabled": true,
    "uri": "mongodb+srv://USER:PASS@cluster.mongodb.net/?retryWrites=true",
    "db_name": "llmai",
    "embed_model": "nomic-embed-text",
    "auto_recall_at_startup": true,
    "recall_limit": 3
  }
}
```

Env vars always win over config.json.

### 6. Verify

Run a session, ask the agent something, then `/reset` (CLI) or click
*Reset* (Web UI). Start a new session in the same workspace — it should
greet you with:

```
[Memory from prior sessions in this workspace]
• (2026-05-23) Investigated the Groq cloud fallback...
```

Then ask: *"Have we ever seen this rate-limit error before?"* — the agent
should call `recall_memory` and get hits from your prior session.

## The `recall_memory` tool

```jsonc
{
  "name": "recall_memory",
  "args": {
    "query": "rate limiting on /api/chat",
    "limit": 5,         // optional, default 5, max 20
    "scope": "both"     // summaries | knowledge | both
  }
}
```

Returns a markdown-ish ranked snippet list with timestamp and scope tag.
Read-only — auto-approved by the permission system.

## What's NOT stored

- **No file contents** — extracted knowledge stores principles
  ("authentication uses bcrypt", "API client lives in `client/`"), not
  verbatim file bodies. Snippets store file path + line range, not the
  code itself.
- **No raw prompts unless you opt in to session retention** — the
  `sessions` collection contains the full transcript by design (for
  `/show last-session` style features later); if you want to disable
  this, set `memory.skip_session_retention: true` (TODO — for v1, you
  can manually `db.sessions.drop()` periodically).
- **No cross-workspace leakage** — every query is filtered by
  `workspace_id`. The `recall_memory` tool refuses to search across
  workspaces.

## Cost on Atlas free tier

- Storage: ≤512 MB. Each session ≈10–50 KB, each summary ≈2 KB, each
  knowledge item ≈1 KB. You can fit thousands of sessions.
- Connections: 500 concurrent (llmai uses 1 per agent).
- Vector Search: included on M0 free tier. No extra cost.

For heavy use, M10 dedicated ($60/mo) gives you 10 GB and predictable
latency.

## Privacy notes

- Atlas connection string contains credentials → keep it in env vars or
  `.env`, never commit to git. The `.env.example` template ships with
  `LLMAI_MEMORY_URI=` empty.
- Atlas data is encrypted at rest by default. Use TLS-only connections
  (the `mongodb+srv://` URI does this automatically).
- llmai never sends data to Atlas unless you set
  `LLMAI_MEMORY_ENABLED=true`. Default is off — the local-first stance
  is preserved.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Memory enabled but no URI configured` | Forgot the connection string | Set `LLMAI_MEMORY_URI` |
| `Memory store connect failed: ... timed out` | IP not allowed | Add your IP in Atlas → Network Access |
| `pymongo not installed` | Skipped the optional install | `pip install -e ".[memory]"` |
| `Embedding endpoint unreachable (model=nomic-embed-text)` | Embed model not pulled | `ollama pull nomic-embed-text` |
| `recall_memory` returns "No prior memory matches" but you know there's data | Vector index still building, or fallback to lexical found nothing | Wait ~2 min for index; or check `db.summaries.countDocuments()` |
| `command createSearchIndex not found` | Self-hosted MongoDB (not Atlas) | Memory still works in lexical-fallback mode; for full semantic recall, use Atlas |

## Skill promotion from knowledge

llmai automatically promotes frequently-recalled knowledge into stable
**skills** — pieces of reusable context auto-injected into every new
session in the same workspace. The mechanism:

1. Each call to `recall_memory` increments `recall_count` on every
   knowledge document it returns.
2. When a knowledge doc crosses the threshold (default 3) and hasn't
   been promoted yet, an entry is created in a fourth collection
   `skills`:
   ```
   skills/
     _id, workspace_id, name (auto-slug), content (≤200 chars),
     source_knowledge_id, created_at, last_used_at,
     usage_count, active (bool)
   ```
3. At the start of every new session, up to 5 active skills (most-
   recently-used first) are loaded and appended as a second system
   message:
   ```
   [Active skills for this workspace]
   • auth-bcrypt-password: Authentication uses bcrypt for hashing
   • api-client-location: REST API client lives in client/ ...
   ```

Tune via `config.json`:
```json
{
  "memory": {
    "skill_promote_threshold": 3,
    "skill_inject_limit": 5
  }
}
```

Env overrides: `LLMAI_SKILL_PROMOTE_THRESHOLD`, `LLMAI_SKILL_INJECT_LIMIT`.

### Managing skills (CLI)

| Command | What |
|---------|------|
| `/skills` | List active skills with usage counts |
| `/skills view <name>` | Show full content + provenance |
| `/skills disable <name>` | Stop injection (soft delete) |
| `/skills delete <name>` | Hard delete |

A skill is automatically named via slug of the first ~5 meaningful words
of its source knowledge fact. Name collisions append `-2`, `-3`, etc.

## Where the code lives

| Path | Purpose |
|------|---------|
| `llmai/memory/store.py` | MongoDB client, schema, vector search, skill CRUD |
| `llmai/memory/embeddings.py` | Ollama embedding wrapper |
| `llmai/memory/recall_tool.py` | The `recall_memory` tool the agent calls |
| `llmai/memory/skills.py` | Slug helper + system-message builder |
| `llmai/agent.py` | Memory + skill lifecycle hooks in the sync CLI loop |
| `server/agent_ws.py` | Same hooks in the async WS loop |
| `scripts/setup_atlas_indexes.py` | One-time index creation |
