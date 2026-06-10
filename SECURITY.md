# Security Policy

## Supported versions

LLMai is in active development. The `master` branch and the most-recent
tagged release receive security fixes.

| Version | Supported |
|---------|-----------|
| `master` | ✓ |
| latest tagged release | ✓ |
| older releases | ✗ |

## Reporting a vulnerability

**Do not open a public issue** for security problems.

Instead, email **sechan9999@gmail.com** with subject prefix `[LLMai security]`.
Please include:

- A description of the vulnerability and its impact
- Reproduction steps
- The version / commit SHA you tested against
- Any proof-of-concept code (if applicable)

I will acknowledge within **72 hours** and, where possible, provide a
remediation timeline within **7 days**.

Coordinated disclosure is appreciated — give me time to fix the issue
before publishing details.

## What counts as a security issue

In scope:

- Path traversal that escapes the workspace sandbox
- Shell-command injection that bypasses the dangerous-command blocklist
- Permission-system bypasses (a tool that mutates state without
  user approval)
- Leaked credentials in telemetry attributes (raw prompts, file contents,
  API tokens)
- Cross-workspace data leakage in the memory or knowledge layers
- Vulnerabilities in optional partner integrations (Atlas / Dynatrace /
  Elastic) caused by LLMai's client code

Out of scope:

- Bugs that only trigger when the user explicitly approves a destructive
  command (LLMai trusts approved actions — that's the design)
- Vulnerabilities in upstream dependencies (please report to them directly;
  if it materially affects LLMai I'll cut a release after the fix lands)
- Issues that require a malicious local user with shell access to the
  same machine

## Security posture

- **Workspace sandbox** — file operations are restricted to
  `WORKSPACE_ROOT` (see `llmai/tools.py:_validate_path`). Path traversal
  via `..` resolves to absolute path and is blocked
- **Dangerous-command blocklist** — `_DANGEROUS_PATTERNS` in
  `llmai/tools.py` blocks recursive deletes, fork bombs, filesystem
  formats, raw device writes, system power commands
- **Permission gates** — every mutating tool defaults to `ask` (see
  `llmai/permissions.py:DEFAULT`)
- **Local-first by default** — no network calls unless an `LLMAI_*_ENABLED`
  env var is explicitly set to `true`
- **No raw prompts in telemetry** — OTel span attributes carry metadata
  only (lengths, latencies, outcomes). `tool.args.preview` is truncated
  to 200 chars
- **Per-workspace memory scoping** — `sha256(absolute_path)[:16]` filters
  every read and write; cross-workspace queries are refused
- **TLS for cloud connections** — `mongodb+srv://` and Elastic Cloud
  endpoints use TLS by default
- **MCP servers are untrusted by default** — every tool discovered from
  an MCP server defaults to `ask`; auto-approval requires an explicit
  per-server `allow` list. Servers run as local stdio subprocesses (no
  sockets), and only the env vars named in their config block are passed
  beyond the inherited environment

## What leaves your machine (threat model)

| Configuration | Data that leaves the machine |
|---------------|------------------------------|
| Core (default) | Nothing — model, tools, and files are all local |
| + Telemetry | Span metadata only (latencies, token counts, outcomes) to your configured OTel endpoint; no prompts or file contents |
| + Memory (Atlas) | Session summaries, extracted facts, and their embeddings to your Atlas cluster |
| + Elastic | Search queries and ingested GitLab issues/logs/docs to your Elastic cluster |
| + MCP | Whatever the configured MCP server sends to its own backend (e.g. queries to your Atlas cluster); the MCP wire protocol itself stays on localhost stdio |

## Known limitations

- LLMai trusts the local LLM. A prompt-injection attack via a malicious
  file you ask the model to read can cause it to *attempt* destructive
  commands. The permission system stops execution, but it can still
  attempt to write files within the workspace (one approval away from
  damage). This is the inherent risk of agent autonomy — the mitigation
  is the permission gate, not an absolute defense
- The Web UI is single-user. Do not expose `llmai-server` (port 7777) to
  untrusted networks
- Telemetry, when enabled, ships span metadata to whatever endpoint you
  configure. Verify your collector's network path before pointing it at
  production data
