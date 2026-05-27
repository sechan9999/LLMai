"""
Integration test fixtures.

These tests need real backends running:
  - Ollama at $OLLAMA_URL (default http://localhost:11434), with both
    qwen2.5-coder (or any chat model) and nomic-embed-text pulled
  - Elasticsearch at $LLMAI_ELASTIC_URL (default http://localhost:9200)
  - MongoDB at $LLMAI_TEST_MONGO_URI (no default — tests skip if unset)

Each test is auto-skipped when its required backend isn't reachable so
the suite stays runnable on partial setups.

Run integration tests explicitly:
  pytest tests/integration/ -m integration -v

They're NOT collected by the default `pytest tests/` run (see
pyproject.toml `addopts`).
"""
from __future__ import annotations

import os

import pytest
import requests


def _reachable(url: str, *, timeout: float = 2.0) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code < 500
    except Exception:
        return False


@pytest.fixture(scope="session")
def ollama_url() -> str:
    url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    if not _reachable(f"{url}/api/tags"):
        pytest.skip(f"Ollama not reachable at {url}")
    return url


@pytest.fixture(scope="session")
def ollama_has_embed_model(ollama_url: str) -> bool:
    try:
        r = requests.get(f"{ollama_url}/api/tags", timeout=3)
        models = [m.get("name", "") for m in r.json().get("models", [])]
        return any(m.startswith("nomic-embed-text") for m in models)
    except Exception:
        return False


@pytest.fixture(scope="session")
def elastic_url() -> str:
    url = os.environ.get("LLMAI_ELASTIC_URL", "http://localhost:9200")
    if not _reachable(f"{url}/_cluster/health"):
        pytest.skip(f"Elasticsearch not reachable at {url}")
    return url


@pytest.fixture(scope="session")
def mongo_uri() -> str:
    uri = os.environ.get("LLMAI_TEST_MONGO_URI")
    if not uri:
        pytest.skip("LLMAI_TEST_MONGO_URI not set — skipping memory integration tests")
    return uri
