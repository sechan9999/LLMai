"""
GitLab tools for the llmai agent.

When ``GITLAB_TOKEN`` is set, this module exposes a set of OpenAI-compatible
tools that let the agent triage issues, manage merge requests, and read CI
pipeline logs. The aim is the demo loop:

    user: "the pipeline on MR !42 is red, fix it"
    agent: gitlab_get_mr → gitlab_list_pipelines → gitlab_get_job_log
           → read/edit local files → run_command(git push)
           → gitlab_comment_mr

Configuration (all optional except the token):

    GITLAB_TOKEN     personal access token with ``api`` scope (required)
    GITLAB_URL       base URL, default ``https://gitlab.com``
    GITLAB_PROJECT   ``group/repo`` path; if unset, derived from
                     ``git remote get-url origin``
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import Any
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)


# ── Configuration helpers ────────────────────────────────────────────────────

def is_gitlab_enabled() -> bool:
    """Return True when GitLab integration should expose its tools."""
    return bool(os.environ.get("GITLAB_TOKEN"))


def _detect_project_from_git() -> str | None:
    """Parse ``git remote get-url origin`` for a GitLab ``group/repo`` path.

    Returns None when not in a git repo, no origin remote, or the remote
    isn't a recognizable GitLab URL.
    """
    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return None
        url = out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    # https://gitlab.com/group/sub/repo.git  →  group/sub/repo
    m = re.match(r"https?://[^/]+/(.+?)(?:\.git)?$", url)
    if m:
        return m.group(1)
    # git@gitlab.com:group/sub/repo.git      →  group/sub/repo
    m = re.match(r"[\w.-]+@[^:]+:(.+?)(?:\.git)?$", url)
    if m:
        return m.group(1)
    return None


# ── HTTP client ──────────────────────────────────────────────────────────────

class GitLabError(RuntimeError):
    """Raised when the GitLab API returns an error or auth fails."""


class GitLabClient:
    """Minimal GitLab REST client (v4)."""

    def __init__(
        self,
        token: str | None = None,
        url: str | None = None,
        project: str | None = None,
    ):
        self.token = token or os.environ.get("GITLAB_TOKEN")
        if not self.token:
            raise GitLabError(
                "GITLAB_TOKEN is not set. Create a personal access token with "
                "'api' scope at <gitlab>/-/user_settings/personal_access_tokens."
            )
        self.url = (url or os.environ.get("GITLAB_URL") or "https://gitlab.com").rstrip("/")
        self.project = project or os.environ.get("GITLAB_PROJECT") or _detect_project_from_git()
        if not self.project:
            raise GitLabError(
                "GITLAB_PROJECT not set and no git origin found. "
                "Set it to e.g. 'group/repo'."
            )
        self._project_enc = quote(self.project, safe="")
        self._headers = {"PRIVATE-TOKEN": self.token}

    # ---- low-level HTTP ----

    def _request(self, method: str, path: str, **kw: Any) -> Any:
        endpoint = f"{self.url}/api/v4{path}"
        try:
            resp = requests.request(
                method, endpoint, headers=self._headers, timeout=20, **kw
            )
        except requests.RequestException as e:
            raise GitLabError(f"network error: {e}") from e
        if resp.status_code >= 400:
            raise GitLabError(
                f"{method} {path} → {resp.status_code}: {resp.text[:300]}"
            )
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def get(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path: str, json: dict | None = None) -> Any:
        return self._request("POST", path, json=json)

    # ---- formatting helpers ----

    def _proj(self, suffix: str) -> str:
        return f"/projects/{self._project_enc}{suffix}"


# ── Module-level singleton (lazy) ────────────────────────────────────────────

_client: GitLabClient | None = None


def _get_client() -> GitLabClient:
    global _client
    if _client is None:
        _client = GitLabClient()
    return _client


def reset_client() -> None:
    """Drop the cached client (used by tests)."""
    global _client
    _client = None


# ── Formatting ───────────────────────────────────────────────────────────────

def _fmt_user(u: dict | None) -> str:
    if not u:
        return "?"
    return u.get("username") or u.get("name") or "?"


def _fmt_issue_summary(issue: dict) -> str:
    labels = ", ".join(issue.get("labels") or []) or "—"
    return (
        f"#{issue.get('iid')} [{issue.get('state')}] "
        f"{issue.get('title')}  "
        f"(by {_fmt_user(issue.get('author'))}, labels: {labels})"
    )


def _fmt_mr_summary(mr: dict) -> str:
    return (
        f"!{mr.get('iid')} [{mr.get('state')}] "
        f"{mr.get('title')}  "
        f"({mr.get('source_branch')} → {mr.get('target_branch')}, "
        f"by {_fmt_user(mr.get('author'))})"
    )


def _fmt_pipeline_summary(p: dict) -> str:
    return (
        f"#{p.get('id')} [{p.get('status')}] "
        f"ref={p.get('ref')} sha={(p.get('sha') or '')[:8]} "
        f"web={p.get('web_url')}"
    )


# ── Tool implementations ─────────────────────────────────────────────────────

def gitlab_list_issues(state: str = "opened", labels: str | None = None,
                       search: str | None = None, limit: int = 20) -> str:
    c = _get_client()
    items = c.get(c._proj("/issues"),
                  state=state, labels=labels, search=search, per_page=min(limit, 50))
    if not items:
        return f"No issues matching state={state} labels={labels} search={search}"
    return "\n".join(_fmt_issue_summary(i) for i in items[:limit])


def gitlab_get_issue(iid: int) -> str:
    c = _get_client()
    issue = c.get(c._proj(f"/issues/{int(iid)}"))
    notes = c.get(c._proj(f"/issues/{int(iid)}/notes"), sort="asc", per_page=20) or []
    body = issue.get("description") or "(no description)"
    lines = [
        _fmt_issue_summary(issue),
        f"Web: {issue.get('web_url')}",
        "",
        "Description:",
        body[:2000],
    ]
    if notes:
        lines += ["", f"Comments ({len(notes)}):"]
        for n in notes[-10:]:
            txt = (n.get("body") or "").splitlines()
            preview = txt[0][:140] if txt else ""
            lines.append(f"  · {_fmt_user(n.get('author'))}: {preview}")
    return "\n".join(lines)


def gitlab_create_issue(title: str, description: str = "",
                        labels: str | None = None) -> str:
    c = _get_client()
    issue = c.post(c._proj("/issues"),
                   json={"title": title, "description": description, "labels": labels})
    return f"Created issue #{issue['iid']}: {issue['web_url']}"


def gitlab_comment_issue(iid: int, body: str) -> str:
    c = _get_client()
    note = c.post(c._proj(f"/issues/{int(iid)}/notes"), json={"body": body})
    return f"Commented on issue #{iid} (note id={note.get('id')})"


def gitlab_list_mrs(state: str = "opened", search: str | None = None,
                    limit: int = 20) -> str:
    c = _get_client()
    items = c.get(c._proj("/merge_requests"),
                  state=state, search=search, per_page=min(limit, 50))
    if not items:
        return f"No merge requests matching state={state} search={search}"
    return "\n".join(_fmt_mr_summary(m) for m in items[:limit])


def gitlab_get_mr(iid: int, include_diff: bool = False) -> str:
    c = _get_client()
    mr = c.get(c._proj(f"/merge_requests/{int(iid)}"))
    notes = c.get(c._proj(f"/merge_requests/{int(iid)}/notes"),
                  sort="asc", per_page=20) or []
    lines = [
        _fmt_mr_summary(mr),
        f"Web: {mr.get('web_url')}",
        "",
        "Description:",
        (mr.get("description") or "(no description)")[:2000],
    ]
    if include_diff:
        changes = c.get(c._proj(f"/merge_requests/{int(iid)}/changes"))
        diffs = changes.get("changes") or []
        lines += ["", f"Changed files ({len(diffs)}):"]
        for d in diffs[:30]:
            lines.append(f"  {d.get('new_path')} ({'new' if d.get('new_file') else 'modified'})")
    if notes:
        lines += ["", f"Comments ({len(notes)}):"]
        for n in notes[-10:]:
            txt = (n.get("body") or "").splitlines()
            preview = txt[0][:140] if txt else ""
            lines.append(f"  · {_fmt_user(n.get('author'))}: {preview}")
    return "\n".join(lines)


def gitlab_create_mr(source_branch: str, target_branch: str, title: str,
                     description: str = "") -> str:
    c = _get_client()
    mr = c.post(c._proj("/merge_requests"), json={
        "source_branch": source_branch,
        "target_branch": target_branch,
        "title": title,
        "description": description,
    })
    return f"Created MR !{mr['iid']}: {mr['web_url']}"


def gitlab_comment_mr(iid: int, body: str) -> str:
    c = _get_client()
    note = c.post(c._proj(f"/merge_requests/{int(iid)}/notes"), json={"body": body})
    return f"Commented on MR !{iid} (note id={note.get('id')})"


def gitlab_list_pipelines(status: str | None = None, ref: str | None = None,
                          limit: int = 10) -> str:
    c = _get_client()
    items = c.get(c._proj("/pipelines"),
                  status=status, ref=ref, per_page=min(limit, 50))
    if not items:
        return f"No pipelines matching status={status} ref={ref}"
    return "\n".join(_fmt_pipeline_summary(p) for p in items[:limit])


def gitlab_get_pipeline(pipeline_id: int) -> str:
    c = _get_client()
    pipe = c.get(c._proj(f"/pipelines/{int(pipeline_id)}"))
    jobs = c.get(c._proj(f"/pipelines/{int(pipeline_id)}/jobs")) or []
    lines = [
        _fmt_pipeline_summary(pipe),
        f"Created: {pipe.get('created_at')}  Duration: {pipe.get('duration')}s",
        "",
        f"Jobs ({len(jobs)}):",
    ]
    for j in jobs:
        lines.append(
            f"  [{j.get('status')}] {j.get('stage')} / {j.get('name')}  "
            f"(id={j.get('id')})"
        )
    return "\n".join(lines)


def gitlab_get_job_log(job_id: int, tail: int = 200) -> str:
    """Return the last *tail* lines of a job's trace log."""
    c = _get_client()
    # /trace returns plain text, not JSON
    endpoint = f"{c.url}/api/v4{c._proj(f'/jobs/{int(job_id)}/trace')}"
    try:
        resp = requests.get(endpoint, headers=c._headers, timeout=20)
    except requests.RequestException as e:
        raise GitLabError(f"network error: {e}") from e
    if resp.status_code >= 400:
        raise GitLabError(f"GET trace → {resp.status_code}: {resp.text[:300]}")
    text = resp.text or "(empty trace)"
    lines = text.splitlines()
    if len(lines) > tail:
        return "… (truncated)\n" + "\n".join(lines[-tail:])
    return text


# ── Tool registry (OpenAI function-calling format) ───────────────────────────

GITLAB_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "gitlab_list_issues",
            "description": "List GitLab issues in the current project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {"type": "string", "description": "opened | closed | all"},
                    "labels": {"type": "string", "description": "Comma-separated labels"},
                    "search": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max issues to return"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitlab_get_issue",
            "description": "Fetch a single issue with description and recent comments.",
            "parameters": {
                "type": "object",
                "properties": {"iid": {"type": "integer", "description": "Issue iid"}},
                "required": ["iid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitlab_create_issue",
            "description": "Open a new issue in the current GitLab project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "labels": {"type": "string", "description": "Comma-separated labels"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitlab_comment_issue",
            "description": "Post a comment on a GitLab issue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "iid": {"type": "integer"},
                    "body": {"type": "string"},
                },
                "required": ["iid", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitlab_list_mrs",
            "description": "List merge requests in the current project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {"type": "string", "description": "opened | merged | closed | all"},
                    "search": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitlab_get_mr",
            "description": (
                "Fetch a merge request — title, description, comments, and "
                "optionally the file list of its diff."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "iid": {"type": "integer", "description": "MR iid"},
                    "include_diff": {
                        "type": "boolean",
                        "description": "Include the list of changed files",
                    },
                },
                "required": ["iid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitlab_create_mr",
            "description": "Open a new merge request from source_branch into target_branch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_branch": {"type": "string"},
                    "target_branch": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["source_branch", "target_branch", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitlab_comment_mr",
            "description": "Post a comment on a merge request.",
            "parameters": {
                "type": "object",
                "properties": {
                    "iid": {"type": "integer"},
                    "body": {"type": "string"},
                },
                "required": ["iid", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitlab_list_pipelines",
            "description": "List recent CI pipelines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "running | success | failed | canceled | …",
                    },
                    "ref": {"type": "string", "description": "Branch or tag"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitlab_get_pipeline",
            "description": "Get a pipeline including its jobs (status, stage, name, id).",
            "parameters": {
                "type": "object",
                "properties": {"pipeline_id": {"type": "integer"}},
                "required": ["pipeline_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gitlab_get_job_log",
            "description": (
                "Return the last *tail* lines of a CI job's log/trace. "
                "Use after gitlab_get_pipeline to read why a job failed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer"},
                    "tail": {
                        "type": "integer",
                        "description": "Number of trailing lines (default 200)",
                    },
                },
                "required": ["job_id"],
            },
        },
    },
]


GITLAB_TOOL_HANDLERS = {
    "gitlab_list_issues":    gitlab_list_issues,
    "gitlab_get_issue":      gitlab_get_issue,
    "gitlab_create_issue":   gitlab_create_issue,
    "gitlab_comment_issue":  gitlab_comment_issue,
    "gitlab_list_mrs":       gitlab_list_mrs,
    "gitlab_get_mr":         gitlab_get_mr,
    "gitlab_create_mr":      gitlab_create_mr,
    "gitlab_comment_mr":     gitlab_comment_mr,
    "gitlab_list_pipelines": gitlab_list_pipelines,
    "gitlab_get_pipeline":   gitlab_get_pipeline,
    "gitlab_get_job_log":    gitlab_get_job_log,
}


# Read-only tools auto-allow; any state-changing tool requires user approval.
GITLAB_DEFAULT_PERMISSIONS = {
    "gitlab_list_issues":    "allow",
    "gitlab_get_issue":      "allow",
    "gitlab_list_mrs":       "allow",
    "gitlab_get_mr":         "allow",
    "gitlab_list_pipelines": "allow",
    "gitlab_get_pipeline":   "allow",
    "gitlab_get_job_log":    "allow",
    "gitlab_create_issue":   "ask",
    "gitlab_comment_issue":  "ask",
    "gitlab_create_mr":      "ask",
    "gitlab_comment_mr":     "ask",
}
