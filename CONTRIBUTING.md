# Contributing to LLMai

Thanks for considering a contribution. The goal here is short, predictable,
and honest about the bar.

## Ground rules

- LLMai stays **local-first by default**. Any new feature that calls the
  network must be opt-in via an env var that defaults to `false` and must
  degrade gracefully when its backend is unreachable.
- Tools that **mutate state** (write files, run shell, mutate remote
  resources) must default to permission mode `ask`. Read-only tools may
  default to `allow`.
- No telemetry, no analytics, no phone-home. The OpenTelemetry integration
  is opt-in and never carries raw prompts or file contents.

## Getting set up

```bash
git clone https://github.com/sechan9999/LLMai.git
cd LLMai
pip install -e ".[dev,telemetry,memory,elastic]"
ollama serve              # in another terminal
ollama pull qwen2.5-coder
python -m pytest tests/ -q
```

If you only care about a subset, install only the extras you need:
`pip install -e ".[dev,memory]"` etc.

## Where to make changes

| Goal | Path |
|------|------|
| Core agent loop (CLI) | `llmai/agent.py` |
| Async agent loop (Web UI) | `server/agent_ws.py` |
| Add a built-in tool | `llmai/tools.py` (and register in `_BASE_HANDLERS`) |
| Add a GitLab tool | `llmai/gitlab_tools.py` |
| Memory layer (MongoDB Atlas) | `llmai/memory/` |
| Knowledge layer (Elasticsearch) | `llmai/elastic/` |
| Telemetry (OpenTelemetry) | `llmai/telemetry.py` |
| Permission system | `llmai/permissions.py` |
| Web UI | `server/static/index.html` |
| Landing page | `website/index.html` |
| Setup docs | `docs/` |

## Coding conventions

- **Python 3.10+** — use PEP 604 unions (`X | None`), `from __future__ import annotations` where the file has many type hints
- **Type hints** required on all new public functions
- **Docstrings** on public classes and non-trivial functions. One-line
  module docstrings explaining what the file is for
- **Logging**: `logger = logging.getLogger(__name__)`. Warn-once for
  expected-but-noisy conditions
- **No emojis in source code or docs** unless the user explicitly requests them
- **No comments that describe what the next line does** — write code that
  reads itself. Comments are for "why," not "what"
- **80–100 char lines** (ruff enforces 100)
- **Run `ruff check .` before submitting**

## Tests

- New code with no tests will be rejected unless it's pure config or docs
- Unit tests go in `tests/test_<module>.py`
- Integration tests go in `tests/integration/` and are gated by
  `@pytest.mark.integration` so the default `pytest` run stays fast and
  offline
- Run the full suite with `pytest tests/ -q`. Coverage must stay above 70%
  (CI enforces this)

## Graceful degradation is non-negotiable

Every optional layer (telemetry / memory / elastic) must handle:

1. **Disabled** — `LLMAI_*_ENABLED=false`: no init, no overhead
2. **Package missing** — optional dep not installed: log warning, no crash
3. **Bad credentials** — connect fails: log warning, agent loop unaffected
4. **Backend unreachable** — runtime error: best-effort, return empty / default

If your PR adds a new external dependency, it must follow this same pattern.

## Commit messages

Conventional commits, ~70-char subject line, present-tense imperative:

```
feat(memory): promote frequently-recalled knowledge to skills
fix(elastic): cascade RRF -> kNN -> BM25 on basic license
docs: add troubleshooting page
refactor: extract retry decorator into _retry.py
test: cover skill promotion threshold edge cases
```

## PR checklist

Before opening a PR:

- [ ] Tests pass locally (`pytest tests/ -q`)
- [ ] Lint passes (`ruff check .`)
- [ ] Coverage ≥ 70% (CI will fail you otherwise)
- [ ] CHANGELOG.md updated under `[Unreleased]`
- [ ] New env vars / config keys documented in the relevant `docs/*-setup.md`
- [ ] If you added an optional dep, you handled all 4 failure modes above

## What I will NOT merge

- Features that erode the local-first stance without a strong reason
- Telegram / Discord / Slack gateways — that's [Hermes Agent](https://github.com/NousResearch/hermes-agent)'s territory
- Cron / scheduling — conflicts with the explicit-permission stance
- Subagent parallelism — out of scope for a single-loop coding agent
- Anything that sends prompts or file contents to a telemetry backend

## Security

If you find a vulnerability, see `SECURITY.md`. Please don't open a public
issue — email the contact there first.

## License

By contributing, you agree your code is released under the project's MIT license.
