"""
Elasticsearch-backed organizational knowledge search.

Layered design:
  - ``llmai-gitlab-issues``  hybrid keyword + dense vector
  - ``llmai-pipeline-logs``  ES|QL for structured failure analysis
  - ``llmai-docs``           dense vector over markdown
  - ``llmai-agent-logs``     tee'd from Bindplane (llmai's own behavior)

Opt-in. Off by default — set ``LLMAI_ELASTIC_ENABLED=true`` or configure
the ``elastic`` block in config.json. Every operation wraps failures so
the agent loop never crashes because Elastic is unreachable.

Public API:
  - init(config): construct + connect; returns the active client or None
  - is_enabled(): True when client is connected
  - get_client(): the active client (or None)
  - ELASTIC_DEFAULT_PERMISSIONS: tool permission defaults (merged into
                                  PermissionManager.DEFAULT)
"""
from __future__ import annotations

from typing import Optional

# Defined here so permissions.py can import it without pulling in the ES
# client library. Keep this dict free of any module-level imports.
ELASTIC_DEFAULT_PERMISSIONS: dict[str, str] = {
    "search_knowledge": "allow",   # read-only hybrid search
    "query_logs":       "ask",     # raw ES|QL — can be expensive
}

# Lazy-import the client so importing this module never fails when
# elasticsearch isn't installed.
_CLIENT = None


def init(config: Optional[dict] = None):
    """Initialize the Elastic client. Idempotent.

    Returns the active client (or None if disabled / init failed).
    """
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    from .client import ElasticClient  # lazy: avoids hard dep on import
    client = ElasticClient.from_config(config or {})
    if client is not None and client.connect():
        _CLIENT = client
    return _CLIENT


def is_enabled() -> bool:
    return _CLIENT is not None and _CLIENT.connected


def get_client():
    return _CLIENT


__all__ = [
    "ELASTIC_DEFAULT_PERMISSIONS",
    "init",
    "is_enabled",
    "get_client",
]
