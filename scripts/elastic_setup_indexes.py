"""
Create Elasticsearch indices used by llmai memory + knowledge search.

Usage:
  export LLMAI_ELASTIC_URL="http://localhost:9200"
  # optional auth:
  export LLMAI_ELASTIC_API_KEY="..."
  python scripts/elastic_setup_indexes.py

Idempotent: existing indices are left untouched.

Indices created:
  - llmai-gitlab-issues   (hybrid: text + dense_vector 768d)
  - llmai-pipeline-logs   (structured fields for ES|QL)
  - llmai-docs            (hybrid: text + dense_vector 768d)
  - llmai-agent-logs      (sink for OTel logs from Bindplane)
"""
from __future__ import annotations

import os
import sys

try:
    from elasticsearch import Elasticsearch
    from elasticsearch.exceptions import BadRequestError, RequestError
except ImportError:
    sys.stderr.write("elasticsearch package not installed. Run: pip install -e '.[elastic]'\n")
    sys.exit(1)


EMBED_DIM = 768  # nomic-embed-text

INDICES = {
    "llmai-gitlab-issues": {
        "mappings": {
            "properties": {
                "project_id":  {"type": "keyword"},
                "iid":         {"type": "long"},
                "title":       {"type": "text"},
                "description": {"type": "text"},
                "state":       {"type": "keyword"},
                "labels":      {"type": "keyword"},
                "author":      {"type": "keyword"},
                "web_url":     {"type": "keyword"},
                "created_at":  {"type": "date"},
                "updated_at":  {"type": "date"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": EMBED_DIM,
                    "index": True,
                    "similarity": "cosine",
                },
            }
        }
    },
    "llmai-pipeline-logs": {
        "mappings": {
            "properties": {
                "project_id":      {"type": "keyword"},
                "pipeline_id":     {"type": "long"},
                "job_id":          {"type": "long"},
                "job_name":        {"type": "keyword"},
                "status":          {"type": "keyword"},
                "ref":             {"type": "keyword"},
                "commit_sha":      {"type": "keyword"},
                "log":             {"type": "text"},
                "error_signature": {"type": "keyword"},
                "duration_s":      {"type": "float"},
                "@timestamp":      {"type": "date"},
            }
        }
    },
    "llmai-docs": {
        "mappings": {
            "properties": {
                "source_path":  {"type": "keyword"},
                "source_repo":  {"type": "keyword"},
                "title":        {"type": "text"},
                "content":      {"type": "text"},
                "updated_at":   {"type": "date"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": EMBED_DIM,
                    "index": True,
                    "similarity": "cosine",
                },
            }
        }
    },
    "llmai-agent-logs": {
        # Sink for OTel logs from Bindplane. Schema is flexible — Bindplane
        # writes whatever attributes the spans carry. We declare a few
        # well-known fields here so ES|QL queries see proper types.
        "mappings": {
            "properties": {
                "@timestamp":          {"type": "date"},
                "trace.id":            {"type": "keyword"},
                "span.id":             {"type": "keyword"},
                "tool.name":           {"type": "keyword"},
                "tool.args.preview":   {"type": "text"},
                "tool.permission.outcome": {"type": "keyword"},
                "tool.exec.latency_ms":    {"type": "float"},
                "error":               {"type": "boolean"},
            }
        }
    },
}


def main() -> int:
    url = os.environ.get("LLMAI_ELASTIC_URL", "http://localhost:9200")
    api_key = os.environ.get("LLMAI_ELASTIC_API_KEY")
    cloud_id = os.environ.get("LLMAI_ELASTIC_CLOUD_ID")
    kwargs = {}
    if cloud_id:
        kwargs["cloud_id"] = cloud_id
    else:
        kwargs["hosts"] = [url]
    if api_key:
        kwargs["api_key"] = api_key

    try:
        es = Elasticsearch(**kwargs)
        info = es.info()
        print(f"  · connected to {info.get('cluster_name')} "
              f"v{(info.get('version') or {}).get('number')}")
    except Exception as exc:
        sys.stderr.write(f"connect failed: {exc}\n")
        return 1

    for name, body in INDICES.items():
        if es.indices.exists(index=name):
            print(f"  · index exists: {name}")
            continue
        try:
            es.indices.create(index=name, **body)
            print(f"  + created index: {name}")
        except (RequestError, BadRequestError) as exc:
            sys.stderr.write(f"  ! create {name} failed: {exc}\n")
            return 2

    print("\nDone. Try a sanity check:")
    print('  curl -s "$LLMAI_ELASTIC_URL/_cat/indices/llmai-*?v"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
