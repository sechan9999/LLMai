"""
Seed the GitLab demo project for the hackathon video.

Creates in https://gitlab.com/hkchun18/LLMai (override with GITLAB_PROJECT):
  1. An issue: "Login test fails on token refresh"
  2. A branch + commit adding a postmortem note that hints at the root cause
  3. A merge request referencing the issue (the "teammate already solved
     something similar" breadcrumb the agent finds over MCP)

Requires: GITLAB_TOKEN env var with `api` scope.
Usage:    python scripts/seed_gitlab_demo.py
Idempotent: re-running skips items whose titles already exist.
"""
import os
import sys
from urllib.parse import quote

import requests

GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
PROJECT = os.environ.get("GITLAB_PROJECT", "hkchun18/LLMai")
TOKEN = os.environ.get("GITLAB_TOKEN")

ISSUE_TITLE = "Login test fails on token refresh"
ISSUE_BODY = """\
`test_expired_token_is_refreshed` started failing in `workspace/demo-login/`:

- Expired tokens are **never refreshed** (old token returned forever)
- Valid tokens get **reissued on every call** (session churn)

Both symptoms point at `TokenManager.needs_refresh()` in `auth.py`.
Repro: `pytest workspace/demo-login/ -q`
"""

BRANCH = "docs/token-refresh-postmortem"
MR_TITLE = "docs: postmortem — auth client token refresh inversion"
MR_BODY = """\
Writing down what we found in the **auth client** last quarter so we stop
re-discovering it: the `needs_refresh` predicate was **inverted** — it
compared `time.time() < expires_at` instead of `>=`, so expired tokens
were treated as fresh and fresh tokens as expired.

If you ever see "expired token never refreshed + valid token reissued
every call" together, check the comparison direction first.

Related: #{issue_iid}
"""

NOTE_PATH = "docs/notes/token-refresh-postmortem.md"
NOTE_CONTENT = """\
# Postmortem: token refresh inversion (auth client)

Symptom pair: expired tokens never refreshed AND valid tokens reissued
on every call. Root cause: inverted freshness comparison in
`needs_refresh()` — `<` where `>=` was intended. One-character fix.
"""


def api(method: str, path: str, **kwargs):
    url = f"{GITLAB_URL}/api/v4/{path}"
    r = requests.request(
        method, url, headers={"PRIVATE-TOKEN": TOKEN}, timeout=15, **kwargs
    )
    if r.status_code >= 400:
        print(f"  ! {method} {path} -> {r.status_code}: {r.text[:200]}")
    return r


def main() -> int:
    if not TOKEN:
        print("GITLAB_TOKEN is not set. Create a PAT with `api` scope at")
        print(f"  {GITLAB_URL}/-/user_settings/personal_access_tokens")
        return 1

    pid = quote(PROJECT, safe="")
    proj = api("GET", f"projects/{pid}")
    if proj.status_code != 200:
        print(f"Cannot access project {PROJECT} — check token scope/membership.")
        return 1
    default_branch = proj.json().get("default_branch", "main")
    print(f"Project OK: {PROJECT} (default branch: {default_branch})")

    # 1. Issue
    existing = api("GET", f"projects/{pid}/issues",
                   params={"search": ISSUE_TITLE, "state": "opened"}).json()
    if any(i["title"] == ISSUE_TITLE for i in existing):
        issue = next(i for i in existing if i["title"] == ISSUE_TITLE)
        print(f"Issue exists: #{issue['iid']}")
    else:
        issue = api("POST", f"projects/{pid}/issues",
                    data={"title": ISSUE_TITLE, "description": ISSUE_BODY}).json()
        print(f"Issue created: #{issue['iid']} — {issue['web_url']}")

    # 2. Branch + commit (hint note)
    if api("GET", f"projects/{pid}/repository/branches/{quote(BRANCH, safe='')}"
           ).status_code != 200:
        api("POST", f"projects/{pid}/repository/branches",
            data={"branch": BRANCH, "ref": default_branch})
        commit = api("POST", f"projects/{pid}/repository/commits", json={
            "branch": BRANCH,
            "commit_message": "docs: add token refresh postmortem note",
            "actions": [{"action": "create", "file_path": NOTE_PATH,
                         "content": NOTE_CONTENT}],
        })
        print(f"Branch + commit: {BRANCH} ({commit.status_code})")
    else:
        print(f"Branch exists: {BRANCH}")

    # 3. Merge request referencing the issue
    mrs = api("GET", f"projects/{pid}/merge_requests",
              params={"search": MR_TITLE, "state": "all"}).json()
    if any(m["title"] == MR_TITLE for m in mrs):
        print("MR exists.")
    else:
        mr = api("POST", f"projects/{pid}/merge_requests", data={
            "source_branch": BRANCH,
            "target_branch": default_branch,
            "title": MR_TITLE,
            "description": MR_BODY.format(issue_iid=issue["iid"]),
        }).json()
        print(f"MR created: !{mr.get('iid')} — {mr.get('web_url')}")

    print("\nDemo prompt for the video:")
    print(f'  "Check GitLab issue #{issue["iid"]} about the failing login test,')
    print('   find any related merge requests or notes, then fix the bug in')
    print('   workspace/demo-login and run the tests."')
    return 0


if __name__ == "__main__":
    sys.exit(main())
