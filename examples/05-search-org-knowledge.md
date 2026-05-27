# Example 5 — Search org knowledge before writing code

**Time:** ~5 minutes (assumes Elastic is up + ingested) · **Layers needed:** Elastic

## Setup

See `docs/elastic-setup.md` for the local Docker compose path. Then:

```bash
export LLMAI_ELASTIC_ENABLED=true
export LLMAI_ELASTIC_URL=http://localhost:9200
export GITLAB_TOKEN=glpat-...
export GITLAB_PROJECT=group/project
make elastic-ingest                # pulls issues + pipeline failures
```

After ingest, two new tools are available to the agent:

- `search_knowledge` — hybrid BM25 + dense-vector over `llmai-gitlab-issues`
  and `llmai-docs` (auto-approved, read-only)
- `query_logs` — raw ES|QL over `llmai-pipeline-logs` and
  `llmai-agent-logs` (permission-gated; can be expensive)

## Prompt — search before writing

> Users are reporting timeouts on `/v1/chat/completions`. Look into it
> **before** you write a fix — has the team seen this before?

The system prompt nudges the model to call `search_knowledge` before
writing code that touches an error path. You'll see something like:

```
⚙  search_knowledge({query='timeouts on /v1/chat/completions',
                     scope='both', limit=5})
   → Found 3 hits:
     [1] llmai-gitlab-issues · score=0.81
         Ollama TCP keep-alive expires after 60s under load
         state=closed · labels=bug,timeout
         https://gitlab.example/.../issues/142
     [2] llmai-docs · score=0.68
         Recommended timeout values for Ollama clients
         docs/ollama-tuning.md
     [3] llmai-gitlab-issues · score=0.63
         Connection reset under sustained load
         state=closed · labels=bug
```

Now the agent has prior art. Its fix references the existing issue's
solution instead of inventing a new approach.

## Prompt — ES|QL analytics

> Which CI jobs failed most this week and why?

The agent calls `query_logs` (asks permission first since it's
potentially expensive):

```
⚙  query_logs(esql=FROM llmai-pipeline-logs
                    | WHERE "@timestamp" > NOW() - 7 days
                          AND status == "failed"
                    | STATS count = COUNT(*) BY error_signature, job_name
                    | SORT count DESC | LIMIT 10)

   → count | error_signature                       | job_name
   ----------------------------------------------------------
       12  | RuntimeError: out of memory          | test
        7  | npm ERR! missing dependency          | lint
        3  | Connection reset                     | integration
```

## Querying the agent's own behavior

The Bindplane collector tees the agent's own OTel logs into Elastic. You
can ask the agent about *itself*:

> How often did `run_command` get denied this week?

```
⚙  query_logs(esql=FROM llmai-agent-logs
                    | WHERE "@timestamp" > NOW() - 7 days
                          AND "tool.name" == "run_command"
                          AND "tool.permission.outcome" == "ask_deny"
                    | STATS denials = COUNT(*) BY "tool.args.preview"
                    | SORT denials DESC | LIMIT 5)
```

## What you learn

- The agent gets *organizational* context, not just *personal* (Atlas) or
  *operational* (Dynatrace)
- Hybrid search means *"chat endpoint throttling"* surfaces an issue
  filed as *"429 under burst load"* — pure semantic match, no shared
  keywords
- ES|QL gives the model a real query language for structured data, not
  just full-text search

## When NOT to use this

- If your team has no shared issue tracker yet, there's nothing to ingest
- For one-shot scripts (no future re-use) the lookup overhead isn't worth
  it — disable with `unset LLMAI_ELASTIC_ENABLED`
