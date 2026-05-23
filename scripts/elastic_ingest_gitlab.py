"""
One-shot ingestion: pull GitLab issues into llmai-gitlab-issues with
embeddings, ready for hybrid search.

Usage:
  export GITLAB_TOKEN=glpat-...
  export GITLAB_PROJECT=group/project   # or comma-separated list
  export LLMAI_ELASTIC_URL=http://localhost:9200
  python scripts/elastic_ingest_gitlab.py [--limit 500]

What it does:
  1. For each configured project, fetches the most recent issues (open +
     closed) from GitLab's REST API.
  2. Embeds title + description via Ollama (nomic-embed-text by default).
  3. Bulk-indexes into Elastic with deterministic _id so re-runs upsert
     instead of duplicating.

Re-run any time to refresh — uses index semantics with stable IDs.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

try:
    from elasticsearch import Elasticsearch
    from elasticsearch.helpers import bulk
except ImportError:
    sys.stderr.write("elasticsearch package not installed. Run: pip install -e '.[elastic]'\n")
    sys.exit(1)

# Reuse llmai's existing GitLab client + embedder
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llmai.gitlab_tools import GitLabClient, GitLabError, _detect_project_from_git  # noqa: E402
from llmai.memory.embeddings import Embedder  # noqa: E402

INDEX = "llmai-gitlab-issues"


def _doc_id(project_id: Any, iid: int) -> str:
    return f"{project_id}#{iid}"


def fetch_issues(gl: GitLabClient, limit: int) -> list[dict]:
    """Pull up to *limit* issues across all states for the client's project."""
    out: list[dict] = []
    per_page = 100
    page = 1
    while len(out) < limit:
        try:
            batch = gl.get(
                gl._proj("/issues"),
                state="all",
                order_by="updated_at",
                per_page=min(per_page, limit - len(out)),
                page=page,
            )
        except GitLabError as exc:
            sys.stderr.write(f"  ! fetch page {page} failed: {exc}\n")
            break
        if not batch:
            break
        out.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return out[:limit]


def ingest_project(project: str, es: Elasticsearch, emb: Embedder, limit: int) -> int:
    """Pull and index issues for one GitLab project."""
    print(f"  · {project}: fetching up to {limit} issues")
    try:
        gl = GitLabClient(project=project)
    except GitLabError as exc:
        sys.stderr.write(f"  ! cannot connect to {project}: {exc}\n")
        return 0

    issues = fetch_issues(gl, limit)
    if not issues:
        print("    (no issues found)")
        return 0

    actions: list[dict[str, Any]] = []
    for issue in issues:
        text = (issue.get("title") or "") + "\n\n" + (issue.get("description") or "")
        embedding = emb.embed(text.strip())
        doc: dict[str, Any] = {
            "project_id":  str(issue.get("project_id")),
            "iid":         issue.get("iid"),
            "title":       issue.get("title"),
            "description": issue.get("description") or "",
            "state":       issue.get("state"),
            "labels":      issue.get("labels") or [],
            "author":      (issue.get("author") or {}).get("username"),
            "web_url":     issue.get("web_url"),
            "created_at":  issue.get("created_at"),
            "updated_at":  issue.get("updated_at"),
        }
        if embedding is not None:
            doc["embedding"] = embedding
        actions.append({
            "_op_type": "index",
            "_index": INDEX,
            "_id": _doc_id(issue.get("project_id"), issue.get("iid")),
            "_source": doc,
        })

    success, errors = bulk(es, actions, raise_on_error=False)
    if errors:
        sys.stderr.write(f"    {len(errors)} bulk errors (first: {errors[0]})\n")
    print(f"    indexed {success}/{len(actions)} issues")
    return int(success)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=500, help="Max issues per project")
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

    embed_model = os.environ.get("LLMAI_ELASTIC_EMBED_MODEL", "nomic-embed-text")
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    emb = Embedder(base_url=ollama_url, model=embed_model)

    total = 0
    for proj in projects:
        total += ingest_project(proj, es, emb, args.limit)
    print(f"\nDone. Total indexed: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
