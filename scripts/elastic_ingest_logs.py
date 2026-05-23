"""
One-shot ingestion: pull GitLab CI pipeline failure logs into
llmai-pipeline-logs with an extracted error_signature, ready for ES|QL.

Usage:
  export GITLAB_TOKEN=glpat-...
  export GITLAB_PROJECT=group/project   # or comma-separated list
  export LLMAI_ELASTIC_URL=http://localhost:9200
  python scripts/elastic_ingest_logs.py [--limit 50]

What it does:
  1. For each project, fetches the most recent failed pipelines.
  2. For each failed pipeline, pulls failed-job logs via the REST API.
  3. Extracts an error_signature (first matching error line) via regex.
  4. Bulk-indexes into Elastic with stable IDs.

Designed to feed ES|QL queries like:

  FROM llmai-pipeline-logs
    | WHERE @timestamp > NOW() - 7 days
    | STATS count = COUNT(*) BY error_signature, job_name
    | SORT count DESC | LIMIT 10
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any

import requests

try:
    from elasticsearch import Elasticsearch
    from elasticsearch.helpers import bulk
except ImportError:
    sys.stderr.write("elasticsearch package not installed. Run: pip install -e '.[elastic]'\n")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llmai.gitlab_tools import GitLabClient, GitLabError, _detect_project_from_git  # noqa: E402

INDEX = "llmai-pipeline-logs"

# Regexes for extracting an error signature from logs. First match wins.
_ERROR_PATTERNS = [
    re.compile(r"^([A-Z][A-Za-z]*Error|[A-Z][A-Za-z]*Exception): (.+)$", re.MULTILINE),
    re.compile(r"^error:\s+(.+)$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^FAILED\s+(.+)$", re.MULTILINE),
    re.compile(r"^npm ERR!\s+(.+)$", re.MULTILINE),
    re.compile(r"^E\s+(.+Error.+)$", re.MULTILINE),  # pytest -E
    re.compile(r"\bSegmentation fault\b", re.IGNORECASE),
    re.compile(r"\bOutOfMemory\w*", re.IGNORECASE),
    re.compile(r"\bENOSPC\b"),
]


def extract_signature(log: str) -> str | None:
    for pat in _ERROR_PATTERNS:
        m = pat.search(log)
        if m:
            sig = re.sub(r"\s+", " ", m.group(0).strip())
            return sig[:160]
    return None


def _doc_id(project: str, job_id: int) -> str:
    return f"{project}#job{job_id}"


def _fetch_job_log(gl: GitLabClient, job_id: int) -> str:
    """The GitLab API returns plain text for job traces, not JSON — fetch raw."""
    endpoint = f"{gl.url}/api/v4{gl._proj(f'/jobs/{job_id}/trace')}"
    try:
        resp = requests.get(endpoint, headers=gl._headers, timeout=30)
        if resp.status_code >= 400:
            return ""
        return resp.text
    except requests.RequestException:
        return ""


def ingest_project(project: str, es: Elasticsearch, limit: int) -> int:
    print(f"  · {project}: fetching up to {limit} failed pipelines")
    try:
        gl = GitLabClient(project=project)
    except GitLabError as exc:
        sys.stderr.write(f"  ! cannot connect to {project}: {exc}\n")
        return 0

    try:
        pipelines = gl.get(
            gl._proj("/pipelines"), status="failed", per_page=min(100, limit),
        ) or []
    except GitLabError as exc:
        sys.stderr.write(f"  ! list_pipelines failed: {exc}\n")
        return 0

    actions: list[dict[str, Any]] = []
    for p in pipelines[:limit]:
        try:
            jobs = gl.get(gl._proj(f"/pipelines/{p['id']}/jobs")) or []
        except GitLabError as exc:
            sys.stderr.write(f"  ! jobs for pipeline {p['id']}: {exc}\n")
            continue
        for job in jobs:
            if job.get("status") != "failed":
                continue
            log = _fetch_job_log(gl, job["id"])
            sig = extract_signature(log or "")
            doc = {
                "project_id":      project,
                "pipeline_id":     p.get("id"),
                "job_id":          job.get("id"),
                "job_name":        job.get("name"),
                "status":          job.get("status"),
                "ref":             p.get("ref"),
                "commit_sha":      (p.get("sha") or "")[:12],
                # Trim log to keep index size sane (last 12 KB usually has the failure)
                "log":             (log or "")[-12000:],
                "error_signature": sig or "unknown",
                "duration_s":      job.get("duration"),
                "@timestamp":      job.get("finished_at") or job.get("created_at"),
            }
            actions.append({
                "_op_type": "index",
                "_index": INDEX,
                "_id": _doc_id(project, job["id"]),
                "_source": doc,
            })

    if not actions:
        print("    (no failed jobs to index)")
        return 0
    success, errors = bulk(es, actions, raise_on_error=False)
    if errors:
        sys.stderr.write(f"    {len(errors)} bulk errors (first: {errors[0]})\n")
    print(f"    indexed {success}/{len(actions)} failed jobs")
    return int(success)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=50, help="Max pipelines per project")
    args = ap.parse_args()

    if not os.environ.get("GITLAB_TOKEN"):
        sys.stderr.write("GITLAB_TOKEN not set.\n")
        return 1
    projects_raw = os.environ.get("GITLAB_PROJECT") or _detect_project_from_git()
    if not projects_raw:
        sys.stderr.write("GITLAB_PROJECT not set and could not detect from git remote.\n")
        return 1
    projects = [p.strip() for p in str(projects_raw).split(",") if p.strip()]

    url = os.environ.get("LLMAI_ELASTIC_URL", "http://localhost:9200")
    api_key = os.environ.get("LLMAI_ELASTIC_API_KEY")
    cloud_id = os.environ.get("LLMAI_ELASTIC_CLOUD_ID")
    kwargs: dict[str, Any] = {}
    if cloud_id:
        kwargs["cloud_id"] = cloud_id
    else:
        kwargs["hosts"] = [url]
    if api_key:
        kwargs["api_key"] = api_key

    es = Elasticsearch(**kwargs)
    if not es.indices.exists(index=INDEX):
        sys.stderr.write(
            f"index {INDEX} does not exist. Run scripts/elastic_setup_indexes.py first.\n"
        )
        return 2

    total = 0
    for proj in projects:
        total += ingest_project(proj, es, args.limit)
    print(f"\nDone. Total indexed: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
