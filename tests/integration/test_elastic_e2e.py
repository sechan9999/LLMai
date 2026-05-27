"""
End-to-end Elastic tests against a real cluster.

Setup before running:
  docker compose -f docker-compose.elastic.yml up -d
  ollama pull nomic-embed-text   # only if you want to test vector search
  LLMAI_ELASTIC_URL=http://localhost:9200 \
    python scripts/elastic_setup_indexes.py

Then:
  pytest tests/integration/test_elastic_e2e.py -m integration -v
"""
from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.integration


def test_connect_and_round_trip(elastic_url):
    """Connect, ping cluster, write + read a doc, clean up."""
    from elasticsearch import Elasticsearch
    es = Elasticsearch(hosts=[elastic_url], request_timeout=10)
    info = es.info()
    assert info["cluster_name"]

    idx = f"llmai-itest-{uuid.uuid4().hex[:8]}"
    try:
        es.indices.create(index=idx)
        es.index(index=idx, id="1", document={"text": "hello world"})
        es.indices.refresh(index=idx)
        r = es.get(index=idx, id="1")
        assert r["_source"]["text"] == "hello world"
    finally:
        es.indices.delete(index=idx, ignore_unavailable=True)


def test_hybrid_search_kNN_fallback(elastic_url, ollama_has_embed_model):
    """Verify the RRF → kNN → BM25 cascade with a seeded doc."""
    if not ollama_has_embed_model:
        pytest.skip("nomic-embed-text not pulled in Ollama")

    os.environ["LLMAI_ELASTIC_ENABLED"] = "true"
    os.environ["LLMAI_ELASTIC_URL"] = elastic_url

    # Reset the cached singleton so init() rebuilds against this URL
    from llmai import elastic as el
    el._CLIENT = None
    client = el.init()
    assert client is not None and client.connected

    issues_idx = client.indices["issues"]
    # `docs` index also seeded by scripts/elastic_setup_indexes.py but
    # this test only writes/reads the issues index.
    # Indices must already exist from scripts/elastic_setup_indexes.py
    raw = client._es
    assert raw.indices.exists(index=issues_idx), \
        f"missing index {issues_idx} — run scripts/elastic_setup_indexes.py first"

    test_id = uuid.uuid4().hex[:8]
    try:
        raw.index(
            index=issues_idx,
            id=f"itest-{test_id}",
            document={
                "project_id": "itest",
                "iid": 1,
                "title": f"itest-{test_id} bug",
                "description": "Rate limiting on /api/chat returns 429 under burst",
                "embedding": client.embedder.embed(
                    "Rate limiting on /api/chat returns 429 under burst"
                ),
                "state": "closed",
            },
        )
        raw.indices.refresh(index=issues_idx)

        # Semantic match — different wording from the indexed text
        hits = client.hybrid_search(
            query="chat endpoint throttling problem",
            scope="issues",
            limit=3,
        )
        assert any(f"itest-{test_id}" in (h.get("title") or "") for h in hits)
    finally:
        raw.delete(index=issues_idx, id=f"itest-{test_id}",
                   ignore=[404])


def test_esql_query(elastic_url):
    """Verify query_logs ES|QL path against the logs index."""
    os.environ["LLMAI_ELASTIC_ENABLED"] = "true"
    os.environ["LLMAI_ELASTIC_URL"] = elastic_url

    from llmai import elastic as el
    el._CLIENT = None
    client = el.init()
    assert client is not None and client.connected

    logs_idx = client.indices["logs"]
    if not client._es.indices.exists(index=logs_idx):
        pytest.skip(f"missing index {logs_idx} — run setup script")

    result = client.run_esql(f"FROM {logs_idx} | LIMIT 1")
    assert "error" not in result or not result["error"], result
    assert "columns" in result
