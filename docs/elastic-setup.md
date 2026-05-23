# Elastic intelligent search for llmai

llmai can search across **organizational knowledge** — GitLab issues, CI
failure logs, project docs, and its own behavior logs — via Elasticsearch.
Two tools are exposed to the agent:

| Tool | What | Permission |
|------|------|------------|
| `search_knowledge` | Hybrid keyword + dense-vector search over issues/docs | `allow` (read-only) |
| `query_logs` | Raw ES\|QL over pipeline logs + agent's own logs | `ask` (can be expensive) |

This complements the other two persistence layers:

| Layer | Source | Scope |
|-------|--------|-------|
| Telemetry (Dynatrace) | OTel spans | Operational |
| Memory (MongoDB Atlas) | Past sessions | Per user, per workspace |
| **Knowledge (Elastic)** | Issues / logs / docs / agent self-logs | **Per org** |

## Indices

| Index | Schema | How populated |
|-------|--------|---------------|
| `llmai-gitlab-issues` | title + description + labels + state + embedding | `scripts/elastic_ingest_gitlab.py` |
| `llmai-pipeline-logs` | structured fields (job_name, error_signature, log) | `scripts/elastic_ingest_logs.py` |
| `llmai-docs` | text + embedding | (TODO: doc ingest — manual for v1) |
| `llmai-agent-logs` | tee'd from Bindplane (llmai's own OTel logs) | Bindplane pipeline |

## Setup (≈10 minutes for the local-Docker path)

### 1. Install the optional dependency

```powershell
pip install -e ".[elastic]"
```

### 2. Start Elasticsearch (local Docker, single-node)

```powershell
docker compose -f docker-compose.elastic.yml up -d
```

- Elasticsearch: `http://localhost:9200`
- Kibana: `http://localhost:5601`

> Security is disabled in this compose for dev simplicity. Don't expose
> these ports beyond `localhost`. For Elastic Cloud, set
> `LLMAI_ELASTIC_CLOUD_ID` + `LLMAI_ELASTIC_API_KEY` instead.

### 3. Create the indices

```powershell
$env:LLMAI_ELASTIC_URL = "http://localhost:9200"
python scripts/elastic_setup_indexes.py
```

Expected output:

```
  · connected to llmai-elasticsearch v8.15.0
  + created index: llmai-gitlab-issues
  + created index: llmai-pipeline-logs
  + created index: llmai-docs
  + created index: llmai-agent-logs
```

### 4. Ingest GitLab issues + pipeline logs (optional)

Needs a GitLab personal access token with `api` scope.

```powershell
$env:GITLAB_TOKEN   = "glpat-..."
$env:GITLAB_PROJECT = "your-group/your-project"   # or comma-separated
$env:LLMAI_ELASTIC_URL = "http://localhost:9200"

python scripts/elastic_ingest_gitlab.py --limit 500
python scripts/elastic_ingest_logs.py --limit 50
```

Both scripts are idempotent — re-run any time to refresh. They use stable
document IDs so re-indexing updates existing records.

### 5. Enable Elastic in llmai

```powershell
$env:LLMAI_ELASTIC_ENABLED = "true"
$env:LLMAI_ELASTIC_URL     = "http://localhost:9200"
llmai-server
```

Or via `config.json`:

```json
{
  "elastic": {
    "enabled": true,
    "url": "http://localhost:9200",
    "embed_model": "nomic-embed-text"
  }
}
```

The agent will see two new tools — `search_knowledge` (auto-approved) and
`query_logs` (asks before each call). The system prompt is nudged to call
`search_knowledge` before writing code that touches error paths or
external APIs.

### 6. (Optional) Tee llmai's own OTel logs to Elastic via Bindplane

If you already have the Dynatrace/Bindplane pipeline running, the bundled
`bindplane/config.yaml` includes an `elasticsearch/agent-logs` exporter.
Set the additional env vars in `.env`:

```
ES_URL=http://elasticsearch:9200
ES_USER=
ES_PASSWORD=
ES_INSECURE=true
```

Now llmai's own tool invocations get logged into `llmai-agent-logs`, and
the agent can query its own behavior:

```
FROM llmai-agent-logs
  | WHERE tool.name == "run_command" AND tool.permission.outcome == "ask_deny"
  | KEEP "@timestamp", "tool.args.preview"
  | LIMIT 20
```

## Example queries

### `search_knowledge`

The agent can call it with natural language:

```json
{
  "name": "search_knowledge",
  "args": {
    "query": "rate limiting on /api/chat broke after deploy",
    "scope": "both",
    "limit": 5
  }
}
```

Returns a ranked list of GitLab issues + docs with hybrid scores.

### `query_logs` (ES\|QL)

```
FROM llmai-pipeline-logs
  | WHERE "@timestamp" > NOW() - 7 days AND status == "failed"
  | STATS count = COUNT(*) BY error_signature, job_name
  | SORT count DESC
  | LIMIT 10
```

Result format is rendered as a compact table.

## Elastic Cloud (production path)

```powershell
$env:LLMAI_ELASTIC_ENABLED  = "true"
$env:LLMAI_ELASTIC_CLOUD_ID = "deployment-name:dXMtZWFzdC0xLmF3cy5j..."
$env:LLMAI_ELASTIC_API_KEY  = "VnVhQ2ZHY0JDZGJrUW0tZTVhT3g6..."
```

Then run `python scripts/elastic_setup_indexes.py` against the cloud
cluster — same script, just different endpoint env vars.

## MCP compatibility

The `search_knowledge` and `query_logs` tools mirror the contract of the
official [`mcp-server-elasticsearch`](https://github.com/elastic/mcp-server-elasticsearch).
Swapping to a real MCP transport is a single-file change in
`llmai/elastic/client.py` (replace HTTP calls with MCP requests). The
tool definitions and the agent loop don't need to change.

## Privacy notes

- Connection credentials live in env vars only. Never commit
  `.env`.
- The agent only sends queries Elastic, never any local code or files.
- `LLMAI_ELASTIC_ENABLED` defaults to `false`. Opt-in.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Elastic enabled but no URL or cloud_id configured` | Forgot env var | Set `LLMAI_ELASTIC_URL` or `LLMAI_ELASTIC_CLOUD_ID` |
| `elasticsearch package not installed` | Skipped optional install | `pip install -e ".[elastic]"` |
| `connect failed: ConnectionError` | Cluster not up yet | `docker compose -f docker-compose.elastic.yml ps` |
| `search_knowledge` returns "No knowledge matches" | Indices empty | Run the ingest scripts |
| `ES\|QL error: ... unknown column ...` | Mapping mismatch | `curl $LLMAI_ELASTIC_URL/llmai-pipeline-logs/_mapping` to verify |
| Hybrid search seems keyword-only | Embeddings unavailable | `ollama pull nomic-embed-text` and re-ingest |

## Where the code lives

| Path | Purpose |
|------|---------|
| `llmai/elastic/client.py` | ES connection, hybrid_search, run_esql |
| `llmai/elastic/search_tool.py` | `search_knowledge` tool definition + handler |
| `llmai/elastic/query_tool.py` | `query_logs` tool definition + handler |
| `scripts/elastic_setup_indexes.py` | One-time index creation |
| `scripts/elastic_ingest_gitlab.py` | Pull issues, embed, index |
| `scripts/elastic_ingest_logs.py` | Pull pipeline failures, extract signatures, index |
| `bindplane/config.yaml` | Logs fan-out (Dynatrace + Elastic) |
| `docker-compose.elastic.yml` | Local single-node ES + Kibana |
