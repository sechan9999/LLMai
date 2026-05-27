# LLMai examples

Concrete walkthroughs you can copy into the agent. Each example shows a
real prompt, what tools the agent ends up calling, and what success looks like.

| # | Example | What it demonstrates |
|---|---------|---------------------|
| 1 | [Find and fix a bug](01-find-and-fix-a-bug.md) | Core agent loop, file read/edit, permission gates |
| 2 | [Refactor with tests as a safety net](02-refactor-with-tests.md) | Multi-step planning, shell command approval |
| 3 | [Triage a GitLab MR with a failing pipeline](03-gitlab-mr-triage.md) | GitLab integration, pipeline log fetch |
| 4 | [Use memory across sessions](04-use-memory-across-sessions.md) | MongoDB Atlas layer, `recall_memory` |
| 5 | [Search org knowledge before writing code](05-search-org-knowledge.md) | Elastic layer, `search_knowledge`, `query_logs` |

## Running them

All five examples assume `llmai-server` is running at
<http://localhost:7777> and Ollama has `qwen2.5-coder` pulled. Examples
4–5 also require the corresponding partner layers enabled — see
`docs/atlas-setup.md` and `docs/elastic-setup.md`.
