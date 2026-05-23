# LLMai hackathon demo — 3-minute video script

**Target length:** 2 min 45 s, hard cap 3 min
**Format:** Screen recording with voiceover, no talking head
**Tone:** Engineer to engineer — show, don't sell

The pitch is **three layers of awareness**, not "AI agent." Plenty of AI
agents exist. The differentiator is that this one *observes itself*,
*remembers across sessions*, and *searches org knowledge* — all locally
controlled, all opt-in, all visible.

---

## Shot list

### 0:00 – 0:15 · The hook (15 s)

**On screen:** Split: a normal chatbot reply on the left ("Sorry, I don't
have context for that") and LLMai on the right calling `recall_memory`
and `search_knowledge` *before* writing code.

**Voiceover:**
> "Every AI coding agent forgets what it did yesterday and ignores what
> your team already learned. LLMai does neither — and it runs entirely
> on your laptop."

### 0:15 – 0:35 · What it is, fast (20 s)

**On screen:** GitHub repo (`github.com/sechan9999/LLMai`), then a quick
`ls llmai/` showing `agent.py`, `tools.py`, `permissions.py`,
`telemetry.py`, `memory/`, `elastic/`.

**Voiceover:**
> "LLMai is a local AI coding agent. Ollama for the model. FastAPI for
> the loop. Eight core tools, agentic loop, explicit permission gates
> for writes and shell — that's the base. The differentiator is three
> optional layers: Dynatrace, MongoDB Atlas, Elastic. All opt-in. None
> required."

### 0:35 – 1:10 · Layer 1 — Dynatrace (35 s)

**On screen:**
1. `make bindplane-up` — Bindplane container starts
2. `export LLMAI_OTEL_ENABLED=true && llmai-server`
3. Ask the agent: *"List the Python files in `llmai/elastic/`"*
4. Agent runs `list_files`. Cut to Dynatrace UI showing the trace:
   `agent.turn → agent.iteration → llm.chat + tool.invocation`
5. Click `tool.invocation` span — show attributes: `tool.name=list_files`,
   `tool.exec.latency_ms`, `tool.permission.outcome=allow`

**Voiceover:**
> "Layer one: operational awareness via Dynatrace. Every tool call is an
> OpenTelemetry span. We can see exactly which tool ran, how long it
> took, whether the user had to approve it, and how many tokens the
> model burned. The agent doesn't know it's being watched — instrumentation
> is in the loop itself, not in the prompt."

### 1:10 – 1:50 · Layer 2 — MongoDB Atlas (40 s)

**On screen:**
1. `make install-memory && python scripts/setup_atlas_indexes.py`
2. `export LLMAI_MEMORY_ENABLED=true LLMAI_MEMORY_URI=...`
3. First session: ask *"refactor the rate-limit handling in `api/chat.js`"*.
   Agent does the work, user types `/reset`.
4. Cut to MongoDB Atlas UI showing 3 new docs in `summaries` and
   `knowledge` collections — point at the embedding field (768-dim).
5. Start a new session in the same workspace. The agent's first response
   includes: *"Memory from prior sessions: (2026-05-23) refactored
   rate-limit handling in api/chat.js — moved cap to per-IP via
   Upstash."*
6. Ask: *"What did we decide about the rate limit again?"* — agent
   calls `recall_memory`, returns the prior decision.

**Voiceover:**
> "Layer two: personal awareness via MongoDB Atlas. Every session is
> stored — transcript, summary, and 3-5 extracted facts, all vector-
> embedded with Ollama's nomic-embed-text running locally. When you
> reopen LLMai in the same workspace, the most recent summaries are
> auto-injected. The agent boots warm. Cross-session continuity that
> survives restarts, machine moves, even directory renames."

### 1:50 – 2:30 · Layer 3 — Elastic (40 s)

**On screen:**
1. `make elastic-up && make elastic-setup`
2. `GITLAB_TOKEN=... GITLAB_PROJECT=... make elastic-ingest` —
   500 issues + 50 failed pipelines indexed
3. Ask: *"Users are reporting timeouts on `/v1/chat/completions`. Look
   into it before you write a fix."*
4. Agent calls `search_knowledge("timeout on chat completions endpoint")`
   — returns 3 hits: a 6-month-old GitLab issue about Ollama TCP keep-
   alives, a pipeline failure with `requests.Timeout`, and a doc on
   recommended timeout values.
5. Agent writes the fix, citing the prior issue in its summary.
6. Bonus: cut to Kibana showing `query_logs` returning ES|QL stats —
   *"the agent's own `run_command` denials this week, grouped by reason."*

**Voiceover:**
> "Layer three: organizational awareness via Elastic. GitLab issues,
> CI failure logs, and docs are ingested with hybrid keyword plus dense
> vector search. The agent is nudged to call `search_knowledge` before
> writing code that touches an error path. So instead of inventing a
> fix, it finds the issue from last quarter where you already figured
> out the answer. And via ES|QL, the agent can query its own behavior
> — Bindplane tees its OpenTelemetry logs into the same Elastic
> cluster."

### 2:30 – 2:45 · The close (15 s)

**On screen:** The README's three-layer table, then the GitHub URL +
`make demo-up`.

**Voiceover:**
> "Three layers, three partners, one agent. All opt-in, all local-first.
> `make demo-up` and you're running. github.com slash sechan9999 slash
> LLMai. Thanks for watching."

---

## Production notes

### Tools / setup needed
- **Recorder:** OBS Studio, 1080p, 30 fps, 60% screen / 40% terminal
- **Voiceover:** record after editing, 16-bit/48 kHz; aim for ~140
  words/min (faster than natural reading; demo videos compress better
  this way)
- **Cuts:** every shot ≤ 8 s; lean on jump cuts and on-screen captions
  for service names ("Dynatrace · trace view", "Atlas · summaries
  collection", "Kibana · Discover")

### Pre-recorded assets
- Atlas free-tier cluster with 5–10 pre-existing sessions so the
  "boots warm" scene has real recall hits
- Dynatrace trial tenant with the indices already warm (~2 min after
  first trace)
- Elastic local cluster with GitLab data already ingested (10+ issues,
  3+ pipeline failures with distinct `error_signature` values)
- Two `.env` files: `.env.demo` (with real credentials, never committed)
  and `.env.example` (the shipped template, all empty)

### What to cut if you go over 3:00
- Drop Kibana ES|QL bonus shot in the Elastic section (saves ~10 s)
- Trim the 0:15 "what it is" section to just the directory listing,
  skip the GitHub repo cut (saves ~5 s)

### What NOT to do
- Don't say "powered by AI" anywhere
- Don't show the chat UI's loading spinners — cut to result
- Don't read the voiceover off the README — it's been rewritten for
  spoken cadence
- Don't show the permission prompt accept-flow more than once (it's
  the same UX everywhere)

---

## Voiceover script (clean copy for the narrator)

> Every AI coding agent forgets what it did yesterday and ignores what
> your team already learned. LLMai does neither — and it runs entirely
> on your laptop.
>
> LLMai is a local AI coding agent. Ollama for the model. FastAPI for
> the loop. Eight core tools, agentic loop, explicit permission gates
> for writes and shell — that's the base. The differentiator is three
> optional layers: Dynatrace, MongoDB Atlas, Elastic. All opt-in. None
> required.
>
> Layer one: operational awareness via Dynatrace. Every tool call is
> an OpenTelemetry span. We can see exactly which tool ran, how long
> it took, whether the user had to approve it, and how many tokens
> the model burned. The agent doesn't know it's being watched —
> instrumentation is in the loop itself, not in the prompt.
>
> Layer two: personal awareness via MongoDB Atlas. Every session is
> stored — transcript, summary, and three to five extracted facts, all
> vector-embedded with Ollama's nomic-embed-text running locally. When
> you reopen LLMai in the same workspace, the most recent summaries
> are auto-injected. The agent boots warm. Cross-session continuity
> that survives restarts, machine moves, even directory renames.
>
> Layer three: organizational awareness via Elastic. GitLab issues,
> CI failure logs, and docs are ingested with hybrid keyword plus
> dense vector search. The agent is nudged to call `search_knowledge`
> before writing code that touches an error path. So instead of
> inventing a fix, it finds the issue from last quarter where you
> already figured out the answer. And via ES|QL, the agent can query
> its own behavior — Bindplane tees its OpenTelemetry logs into the
> same Elastic cluster.
>
> Three layers, three partners, one agent. All opt-in, all local-first.
> `make demo-up` and you're running. github.com slash sechan9999 slash
> LLMai. Thanks for watching.

Word count: ~340. At 140 wpm, ~2 min 26 s of speech. Leaves ~20 s
breathing room for the visuals to land.
