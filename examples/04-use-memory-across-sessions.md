# Example 4 — Use memory across sessions

**Time:** ~5 minutes (assumes Atlas is already set up) · **Layers needed:** MongoDB Atlas memory

## Setup

See `docs/atlas-setup.md` for the one-time cluster + vector-index setup.
Then:

```bash
export LLMAI_MEMORY_ENABLED=true
export LLMAI_MEMORY_URI="mongodb+srv://USER:PASS@cluster.mongodb.net/"
ollama pull nomic-embed-text   # 768d embeddings, runs locally
```

## Day 1 — Build context

In a session, work on something distinctive enough that you'll recognize
the recall. Example:

> Move the rate-limit logic from `api/middleware.py` into a dedicated
> `api/rate_limit.py` module. Use Upstash Redis with a 10-req/minute
> sliding window per IP.

Do the work. End with `/reset` (CLI) or click *Reset* (Web UI). The
session-end hook:

1. Saves the full transcript to the `sessions` collection
2. Asks the LLM to produce a ~200-word summary, embeds it, saves to
   `summaries`
3. Asks the LLM to extract 3–5 reusable facts ("authentication uses
   bcrypt", "rate limit is Upstash sliding window 10/min"), embeds each,
   saves to `knowledge`

## Day 2 — Reopen in the same workspace

Just start a session in the same directory. The first turn now includes
an auto-injected system message:

```
[Memory from prior sessions in this workspace]
• (yesterday) Moved rate-limit logic to api/rate_limit.py.
  Uses Upstash Redis with 10 req/min sliding window per IP.
```

You can also ask explicitly:

> What did we decide about the rate limit again?

The agent calls `recall_memory(query="rate limit decision")` and gets
ranked hits. The recall is **semantic** — *"throttling"*, *"429 errors"*,
or *"abuse prevention"* all surface the same prior work.

## Skill promotion

After the same knowledge fact is recalled 3 times across sessions, it
gets promoted into a stable `skill` that's auto-injected at every new
session start (capped at 5 skills per workspace). See `/skills` to manage
them:

```
/skills
  rate-limit-upstash-sliding    used 4× · 2026-05-26
    Rate limit uses Upstash Redis sliding window 10/min per IP
  auth-bcrypt-password-hashing  used 2× · 2026-05-25
    Authentication uses bcrypt for password hashing
```

## What you learn

- Memory is **per-workspace**, scoped via `sha256(absolute_path)[:16]`.
  Renaming the parent directory keeps memory intact as long as the
  resolved abs path matches
- The agent doesn't need to ask permission to read memory — it's
  auto-approved (read-only, your own data)
- Skills make stable decisions persistent. Disable with
  `/skills disable <name>` if a fact becomes stale

## When this hurts (and how to mitigate)

- **Stale facts.** If you change the rate-limit policy, the old skill
  still gets injected. Run `/skills disable rate-limit-upstash-sliding`
  or just `/skills delete` it
- **Wrong workspace match.** If you symlink dirs, the SHA hash differs.
  Use the same absolute path for the same project
