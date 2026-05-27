# Changelog

All notable changes to LLMai are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_Nothing yet._

---

## [0.2.2] — 2026-05-27

### Changed
- **PyPI distribution name:** `llmai` → `llmai-agent`. The bare `llmai`
  was already taken on PyPI by an unrelated unified-LLM-client project
  uploaded on 2026-05-19. Install with `pip install llmai-agent`. The
  Python import path stays `import llmai`, and all CLI entry points
  (`llmai`, `llmai-server`, `llmai-doctor`) are unchanged.
- Server `/healthz` and OTel `service.version` resource now resolve the
  distribution version under the new package name.

### Fixed
- `release.yml` awk extractor for changelog sections — uses `index()`
  instead of regex brackets so it works portably across awk variants
  (gawk / mawk / busybox).

---

## [0.2.1] — 2026-05-27

First **tagged** release. The 0.2.0 entry below describes the codebase at
the time the partner-integrations work landed (pre-tagging); 0.2.1 is the
production-readiness pass on top.

### Added
- Production-readiness pass: `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`,
  `CODE_OF_CONDUCT.md`, Dependabot config, `py.typed` marker, `examples/`
  directory with 5 concrete walkthroughs.
- `llmai-doctor` diagnostic command — checks Ollama reachability, model
  presence, optional layer connections (telemetry / memory / elastic),
  workspace permissions, and disk space. Also accessible via `/doctor`
  in the CLI REPL.
- Tag-triggered PyPI release workflow (`.github/workflows/release.yml`)
  using Trusted Publishing — no API token in the repo.
- Tag-triggered multi-arch Docker publish to GHCR
  (`.github/workflows/docker.yml`) — linux/amd64 + linux/arm64.
- Coverage reporting in CI (`pytest-cov`, regression floor at 30% — to be
  ratcheted up as integration tests land).
- Optional structured JSON logging via `LLMAI_LOG_FORMAT=json`.
- `/healthz` endpoint on the Web UI server for container health checks.
- Optional `tiktoken` upgrade for token estimation (graceful fallback to
  `chars/4`).
- Unified retry/backoff decorator in `llmai/_retry.py` — applied to the
  Ollama embedding call (transient HTTP failures now retry 3× with
  exponential backoff). Memory store and Elastic client paths reuse
  pymongo/elasticsearch built-in retry; rollout to additional call sites
  is incremental.
- Integration test scaffold (`tests/integration/`) gated by
  `@pytest.mark.integration`.
- Hackathon submission deliverables: `docs/DEVPOST_WRITEUP.md`,
  `docs/YOUTUBE_DESCRIPTION.md`, `docs/LLMai-hackathon-deck.pptx`
  (11-slide, 16:9), `scripts/build_hackathon_deck.py` to regenerate it.

### Changed
- pytest defaults exclude integration tests via `addopts = "-m 'not
  integration' --ignore=tests/integration"` so the suite stays offline-friendly.

---

## [0.2.0] — 2026-05-27

First public release. Tagged after the hackathon partner integrations landed.

### Added
- **Three layers of awareness** (all opt-in, all default off):
  - **Dynatrace** — OpenTelemetry spans for every tool call, routed via a
    bundled Bindplane collector. Spans never carry raw prompts or file
    contents.
  - **MongoDB Atlas** — per-workspace persistent memory backed by Atlas
    Vector Search (768-d cosine, embeddings via local
    `nomic-embed-text`). Recent summaries auto-injected at session start.
    `recall_memory` tool for on-demand semantic recall.
  - **Elastic** — hybrid BM25 + dense-vector search over GitLab issues
    and docs (RRF where licensed, kNN-only fallback elsewhere); ES|QL
    over pipeline failure logs and the agent's own self-logs. Two tools:
    `search_knowledge` (auto-approved) and `query_logs` (permission-gated).
- **Skill promotion from knowledge** — knowledge facts recalled ≥3 times
  auto-promote into a stable `skills` collection and get injected as a
  second system message at session start. `/skills` CLI for managing them.
- **MCP-compatible tool shapes** — `recall_memory`, `search_knowledge`,
  and `query_logs` mirror the official MongoDB Atlas and Elastic MCP
  Server contracts.
- Package renamed `vixcode` → `llmai` to match the project name. Console
  scripts: `llmai`, `llmai-server`. Env-var prefix: `LLMAI_*`.
- `Makefile` with `make demo-up`, `demo-bootstrap`, `demo-status` for
  one-command demo setup.
- Bootstrap scripts: `scripts/setup_atlas_indexes.py`,
  `scripts/elastic_setup_indexes.py`, `scripts/elastic_ingest_gitlab.py`,
  `scripts/elastic_ingest_logs.py`.
- Setup docs: `docs/dynatrace-setup.md`, `docs/atlas-setup.md`,
  `docs/elastic-setup.md`. Hackathon deliverables:
  `docs/DEMO_SCRIPT.md`, `docs/YOUTUBE_DESCRIPTION.md`,
  `docs/DEVPOST_WRITEUP.md`, `docs/LLMai-hackathon-deck.pptx`.

### Fixed
- Landing-page system prompt no longer triggers generic refusals — chips
  are scoped to the LLMai project and a project-aware system prompt is
  prepended in both the local and cloud paths.
- `elasticsearch` Python client pinned `<9` (v9 sends a
  `compatible-with=9` header that ES 8.x rejects).
- `hybrid_search` gracefully cascades RRF → kNN → BM25 so basic-license
  Elasticsearch clusters (no Platinum / no Atlas) still work.

[Unreleased]: https://github.com/sechan9999/LLMai/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/sechan9999/LLMai/releases/tag/v0.2.2
[0.2.1]: https://github.com/sechan9999/LLMai/releases/tag/v0.2.1
[0.2.0]: https://github.com/sechan9999/LLMai/releases/tag/v0.2.0
