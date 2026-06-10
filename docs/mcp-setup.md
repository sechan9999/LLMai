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
