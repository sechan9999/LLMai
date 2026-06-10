# MCP Integration — connect the agent to partner MCP servers

LLMai includes a real [Model Context Protocol](https://modelcontextprotocol.io)
client. Tools served by any spec-compliant MCP server are discovered at
startup and registered into the agent's tool registry, gated by the same
allow/ask/deny permission system as every other tool.

Servers run as **local subprocesses over stdio** — no listening sockets,
no MCP traffic leaves your machine. (Data the MCP server itself sends to
its backend — e.g. your Atlas cluster — follows that server's rules.)

## Prerequisites

```bash
pip install 'llmai-agent[mcp]'      # MCP Python SDK
node --version                       # >= 18, needed for npx-based partner servers
```

## Quick start (GitLab — partner track)

GitLab's **official MCP server** is hosted at `https://gitlab.com/api/v4/mcp`
(OAuth, streamable HTTP). LLMai's client speaks stdio, so the standard
`mcp-remote` bridge proxies it — zero code changes:

```json
"gitlab": {
  "command": "npx",
  "args": ["-y", "mcp-remote", "https://gitlab.com/api/v4/mcp"],
  "allow": []
}
```

First run opens a browser for GitLab OAuth; the token is cached locally
(`~/.mcp-auth`) for subsequent runs. Start with an empty `allow` list,
check the startup log for the exact tool names the server advertises,
then allowlist the read-only ones — anything unlisted simply prompts.

> ⚠️ **Tier requirement (verified 2026-06):** GitLab's official MCP
> server is **Premium/Ultimate only** and requires GitLab Duo + beta
> features enabled on the top-level group. On a free-tier namespace the
> endpoint returns 404 *after* OAuth succeeds. Free-tier users: use the
> community server below, or start a 30-day Ultimate trial on a group.

**Self-managed GitLab / free-tier / headless fallback:** the community
`@zereight/mcp-gitlab` server takes a plain token over stdio, no OAuth:

```json
"gitlab": {
  "command": "npx",
  "args": ["-y", "@zereight/mcp-gitlab"],
  "env": {
    "GITLAB_PERSONAL_ACCESS_TOKEN": "${GITLAB_TOKEN}",
    "GITLAB_API_URL": "https://gitlab.com/api/v4",
    "GITLAB_READ_ONLY_MODE": "true"
  },
  "allow": []
}
```

> **Note — two GitLab paths:** LLMai also ships 11 built-in GitLab tools
> that call the REST API directly (activated by `GITLAB_TOKEN`). Both can
> be active at once; the MCP tools are namespaced `mcp__gitlab__*` so
> there are no collisions. For an MCP-centered workflow, leave
> `GITLAB_TOKEN` unset and use only the MCP server.

## Quick start (MongoDB)

```bash
# in config.json:
{
  "mcp": {
    "enabled": true,
    "servers": {
      "mongodb": {
        "command": "npx",
        "args": ["-y", "mongodb-mcp-server", "--readOnly"],
        "env": { "MDB_MCP_CONNECTION_STRING": "${LLMAI_MEMORY_URI}" },
        "allow": ["find", "aggregate", "list-collections", "list-databases"]
      }
    }
  }
}

llmai-doctor      # verify: mcp sdk ok, mcp:mongodb command found
llmai-server      # tools appear as mcp__mongodb__find, mcp__mongodb__aggregate, ...
```

Or via env: `export LLMAI_MCP_ENABLED=true` (env always wins over config).

## Elastic

```json
"elasticsearch": {
  "command": "npx",
  "args": ["-y", "@elastic/mcp-server-elasticsearch"],
  "env": { "ES_URL": "http://localhost:9200" },
  "allow": ["search", "list_indices", "get_mappings"]
}
```

## How it works

| Step | What happens |
|------|--------------|
| startup | each configured server is spawned; MCP handshake + `tools/list` (10s timeout) |
| registration | tools become `mcp__{server}__{tool}` in the LLM's tool definitions |
| permissions | every MCP tool defaults to **ask**; names in the server's `allow` list auto-approve |
| call | `tools/call` over stdio, 30s timeout (configurable via `mcp.call_timeout_s`) |
| failure | a dead server returns error strings to the LLM; one reconnect attempt is made; the agent never crashes |

## Config reference

| Key | Default | Meaning |
|-----|---------|---------|
| `mcp.enabled` | `false` | master switch (env `LLMAI_MCP_ENABLED` wins) |
| `mcp.call_timeout_s` | `30` | per-call timeout |
| `mcp.servers.{name}.command` | — | executable to spawn (required) |
| `mcp.servers.{name}.args` | `[]` | arguments |
| `mcp.servers.{name}.env` | `{}` | subprocess env; `${VAR}` expands from your environment |
| `mcp.servers.{name}.allow` | `[]` | un-namespaced tool names to auto-approve |

## Troubleshooting

- `llmai-doctor` shows per-server status (SDK installed, command on PATH).
- A server that fails to start is logged as a warning and skipped — the
  rest of the agent works normally.
- Set `LLMAI_MCP_ENABLED=false` to switch the whole layer off without
  touching config.
