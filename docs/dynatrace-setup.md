# Dynatrace observability for vixcode

vixcode instruments both agent loops (CLI + WebSocket server) with OpenTelemetry.
Spans and metrics are exported via OTLP/HTTP. A bundled Bindplane collector
terminates OTLP locally and forwards everything to Dynatrace.

```
vixcode agent ──OTLP/HTTP:4318──► Bindplane (OTel collector) ──► Dynatrace OTLP API
```

## What gets instrumented

| Span | When | Key attributes |
|------|------|----------------|
| `agent.turn` | One per user input | `agent.mode` (cli / ws-native / ws-xml), `agent.provider`, `agent.model`, `agent.input.chars`, `agent.iterations.actual`, `agent.outcome` |
| `agent.iteration` | One per loop iteration | `iteration.number`, `tokens.estimate.before` |
| `llm.chat` | One per LLM call | `llm.model`, `llm.provider`, `llm.messages.count`, `llm.streamed`, `llm.latency_ms`, `llm.tool_calls.requested` |
| `tool.invocation` | One per tool call | `tool.name`, `tool.args.preview` (truncated, no file contents), `tool.permission.outcome` (allow / ask_allow / ask_deny / deny), `tool.permission.latency_ms`, `tool.exec.latency_ms`, `tool.result.chars`, `error` |

Metrics (alongside spans):

- `vixcode.agent.turns` — counter, attrs: mode, provider
- `vixcode.llm.latency` — histogram (ms), attrs: model, provider
- `vixcode.llm.tokens` — histogram, attrs: direction (in/out), model
- `vixcode.tool.invocations` — counter, attrs: tool.name, permission.outcome, error
- `vixcode.tool.latency` — histogram (ms), attrs: tool.name

## Setup (≈5 minutes)

### 1. Install the optional dependencies

```powershell
pip install -e ".[telemetry]"
```

### 2. Get a Dynatrace tenant + token

1. Sign up for a [Dynatrace free trial](https://www.dynatrace.com/trial/) — 15 days, no credit card. You'll get an endpoint like `https://abc12345.live.dynatrace.com`.
2. In Dynatrace: **Access Tokens → Generate new token** with these scopes:
   - `openTelemetryTrace.ingest`
   - `metrics.ingest`
   - `logs.ingest`
3. Copy the token (starts with `dt0c01.…`).

### 3. Start the Bindplane collector

```powershell
copy .env.example .env
# Edit .env, fill in DT_ENDPOINT and DT_API_TOKEN

docker compose -f docker-compose.bindplane.yml up -d
```

Confirm it's listening:

```powershell
curl -s http://localhost:4318
# Returns 405 — that's fine, it means OTLP HTTP is reachable
```

### 4. Enable telemetry in the agent

Either set env vars …

```powershell
$env:VIXCODE_OTEL_ENABLED   = "true"
$env:VIXCODE_OTEL_ENDPOINT  = "http://localhost:4318"
$env:VIXCODE_OTEL_SERVICE_NAME = "vixcode-agent"
vixcode-server
```

… or flip the `telemetry.enabled` block in `config.json`:

```json
{
  "telemetry": {
    "enabled": true,
    "endpoint": "http://localhost:4318",
    "service_name": "vixcode-agent",
    "console": false,
    "headers": {}
  }
}
```

Env vars always win over config.json.

### 5. Verify in Dynatrace

1. Run a few tasks — e.g. ask the agent to list workspace files
2. Open Dynatrace → **Distributed Traces** → filter by `service.name = vixcode-agent`
3. Open one trace — you should see `agent.turn` with `agent.iteration` → `llm.chat` and `tool.invocation` children

For metrics: **Data Explorer** → search `vixcode.tool.invocations`.

## Going direct (skip Bindplane)

If you want to ship straight to Dynatrace without a collector:

```powershell
$env:VIXCODE_OTEL_ENABLED  = "true"
$env:VIXCODE_OTEL_ENDPOINT = "https://abc12345.live.dynatrace.com/api/v2/otlp"
$env:VIXCODE_OTEL_HEADERS  = "Authorization=Api-Token%20dt0c01.YOUR_TOKEN"
vixcode-server
```

Headers are URL-encoded `k=v&k=v`. The literal space in `Api-Token <token>` must be `%20`.

Bindplane is recommended because it (a) buffers when Dynatrace is unreachable, (b) lets you tee to other backends (Honeycomb, Jaeger) without redeploying the agent, and (c) keeps your DT token out of the agent process.

## Privacy notes

- **No raw prompts or file contents** are exported. Span attributes are
  metadata only: name, length, latency, outcome.
- `tool.args.preview` truncates each argument value to 50 chars and the
  whole preview to 200 chars.
- `VIXCODE_OTEL_ENABLED` defaults to `false`. Telemetry is opt-in.

## Local debugging without Dynatrace

```powershell
$env:VIXCODE_OTEL_ENABLED = "true"
$env:VIXCODE_OTEL_CONSOLE = "true"
vixcode-server
```

Spans print to stdout as JSON-ish blobs. Useful for confirming
instrumentation works before you wire up the cloud side.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Telemetry enabled but no endpoint or console exporter configured` | Forgot to set the endpoint | Set `VIXCODE_OTEL_ENDPOINT` or `VIXCODE_OTEL_CONSOLE=true` |
| `OpenTelemetry packages not installed` | Skipped the optional install | `pip install -e ".[telemetry]"` |
| No spans appear in Dynatrace, no errors in agent | Bindplane can't reach Dynatrace | `docker logs vixcode-bindplane` — look for 401 (bad token) or 404 (wrong endpoint path) |
| Spans show up but no metrics | Metric export interval is 15 s | Wait, or restart agent to force flush |
| `401 Unauthorized` in Bindplane logs | Token missing ingest scopes | Regenerate the token with `openTelemetryTrace.ingest` + `metrics.ingest` |

## Where the code lives

| Path | Purpose |
|------|---------|
| `vixcode/telemetry.py` | OTel init + span/metric context managers |
| `vixcode/agent.py` | Sync CLI loop instrumentation |
| `server/agent_ws.py` | Async WebSocket loop instrumentation |
| `bindplane/config.yaml` | OTel collector config (receivers/processors/exporters) |
| `docker-compose.bindplane.yml` | Local Bindplane container |
