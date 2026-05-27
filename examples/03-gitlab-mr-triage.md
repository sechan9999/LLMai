# Example 3 — Triage a GitLab MR with a failing pipeline

**Time:** ~3 minutes · **Layers needed:** GitLab integration

## Setup

```bash
export GITLAB_TOKEN=glpat-...          # personal access token, "api" scope
export GITLAB_PROJECT=group/project    # or auto-detected from git remote
```

11 `gitlab_*` tools become available in the registry once `GITLAB_TOKEN`
is set. See `llmai/gitlab_tools.py` for the full list.

## Prompt

> The pipeline on MR !42 is red. Pull the failing job's log, identify
> the root cause, and post a comment on the MR summarizing what's wrong.

## What the agent does

1. **`gitlab_get_mr 42`** (auto-approved, read-only) — fetches MR title,
   description, source branch, target branch
2. **`gitlab_list_pipelines`** scoped to that MR's source branch — finds
   the latest failed pipeline
3. **`gitlab_get_pipeline <id>`** — surfaces the failing job ID
4. **`gitlab_get_job_log <job_id>`** — pulls the last 200 lines of the
   trace
5. Reads the log, identifies the failure (e.g. `pytest` collection error,
   missing dependency, lint failure)
6. **Asks for permission** to call `gitlab_comment_mr` — you review the
   draft comment
7. **`gitlab_comment_mr 42 "..."`** posts the summary

## Success signal

```
Posted comment on !42:
  > Pipeline failed at job `lint`. ruff reports E501 in
  > src/auth.py:142 (line length 142 > 100). Two-line wrap would fix.
```

## What you learn

- `gitlab_*` read tools auto-approve so triage is fast
- Anything that posts/creates (comment, MR, issue) asks permission so the
  agent can never publish on your behalf without confirmation

## Variations

- *"...and open a fix MR"* — adds `gitlab_create_mr` and local file edits
  to the flow. Several more permission prompts but a complete loop
- *"...and tag the most likely owner from `git blame`"* — adds
  `run_command git blame` to the read phase
- *"only look at the last 3 failed pipelines"* — narrows the scan; useful
  on chatty projects
