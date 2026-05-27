"""
Elasticsearch client wrapper for llmai.

Speaks plain Elasticsearch REST via the official Python client. Two
operations matter:

  - hybrid_search: BM25 keyword + dense vector kNN fused via RRF.
                   Used by the ``search_knowledge`` tool.
  - run_esql:      execute a raw ES|QL query.
                   Used by the ``query_logs`` tool.

All public methods are best-effort: Elastic failures are logged and
swallowed so the agent loop never raises because the index is down.

Connection precedence:
  1. cloud_id + api_key
  2. url + api_key
  3. url (no auth — local Docker dev)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from ..memory.embeddings import Embedder

logger = logging.getLogger(__name__)


# Default index names (overridable via config)
DEFAULT_INDICES = {
    "issues":     "llmai-gitlab-issues",
    "logs":       "llmai-pipeline-logs",
    "docs":       "llmai-docs",
    "agent_logs": "llmai-agent-logs",
}


def _truthy(s: Optional[str]) -> bool:
    return (s or "").strip().lower() in ("1", "true", "yes", "on")


class ElasticClient:
    """Handle for the Elastic backend."""

    def __init__(
        self,
        *,
        url: Optional[str] = None,
        cloud_id: Optional[str] = None,
        api_key: Optional[str] = None,
        verify_certs: bool = True,
        embedder: Optional[Embedder] = None,
        indices: Optional[dict[str, str]] = None,
        request_timeout: int = 30,
    ):
        self.url = url
        self.cloud_id = cloud_id
        self.api_key = api_key
        self.verify_certs = verify_certs
        self.embedder = embedder
        self.indices = {**DEFAULT_INDICES, **(indices or {})}
        self.request_timeout = request_timeout
        self._es = None
        self.connected = False

    # ── Init ─────────────────────────────────────────────────────────────────

    @classmethod
    def from_config(cls, cfg: dict) -> Optional["ElasticClient"]:
        """Build from config + env vars. Returns None when disabled."""
        enabled = _truthy(os.environ.get("LLMAI_ELASTIC_ENABLED")) or bool(
            cfg.get("enabled")
        )
        if not enabled:
            return None
        url = os.environ.get("LLMAI_ELASTIC_URL") or cfg.get("url")
        cloud_id = os.environ.get("LLMAI_ELASTIC_CLOUD_ID") or cfg.get("cloud_id")
        api_key = os.environ.get("LLMAI_ELASTIC_API_KEY") or cfg.get("api_key")
        if not (url or cloud_id):
            logger.warning(
                "Elastic enabled but no URL or cloud_id configured "
                "(set LLMAI_ELASTIC_URL or LLMAI_ELASTIC_CLOUD_ID)."
            )
            return None

        verify = cfg.get("verify_certs")
        verify_certs = bool(verify) if verify is not None else True

        embed_model = (
            os.environ.get("LLMAI_ELASTIC_EMBED_MODEL")
            or cfg.get("embed_model")
            or "nomic-embed-text"
        )
        embed_base = (
            os.environ.get("OLLAMA_URL")
            or cfg.get("embed_url")
            or "http://localhost:11434"
        )
        embedder = Embedder(base_url=embed_base, model=embed_model)

        return cls(
            url=url,
            cloud_id=cloud_id,
            api_key=api_key,
            verify_certs=verify_certs,
            embedder=embedder,
            indices=cfg.get("default_indices"),
        )

    def connect(self) -> bool:
        """Open the connection. Returns True on success."""
        try:
            from elasticsearch import Elasticsearch
        except ImportError:
            logger.warning(
                "Elastic enabled but elasticsearch package not installed; "
                "run: pip install -e '.[elastic]'"
            )
            return False
        kwargs: dict[str, Any] = {"request_timeout": self.request_timeout}
        if self.cloud_id:
            kwargs["cloud_id"] = self.cloud_id
        else:
            kwargs["hosts"] = [self.url]
            kwargs["verify_certs"] = self.verify_certs
        if self.api_key:
            kwargs["api_key"] = self.api_key
        try:
            self._es = Elasticsearch(**kwargs)
            info = self._es.info()
            self.connected = True
            logger.info(
                "Elastic connected: cluster=%s version=%s",
                info.get("cluster_name"),
                (info.get("version") or {}).get("number"),
            )
            return True
        except Exception as exc:
            logger.warning("Elastic connect failed: %s", exc)
            self.connected = False
            return False

    def close(self) -> None:
        if self._es is not None:
            try:
                self._es.close()
            except Exception:
                pass
        self.connected = False

    # ── Hybrid search (BM25 + kNN, fused via RRF) ────────────────────────────

    def hybrid_search(
        self,
        *,
        query: str,
        scope: str = "both",   # issues | docs | both
        limit: int = 5,
    ) -> list[dict]:
        """Hybrid keyword + dense-vector search across selected indices.

        Uses Reciprocal Rank Fusion (Elasticsearch's ``retriever.rrf``).
        Falls back to BM25-only if embeddings aren't available.
        """
        if not self.connected:
            return []

        index_keys = {"issues", "docs"} if scope == "both" else {scope}
        indices = [self.indices[k] for k in index_keys if k in self.indices]
        if not indices:
            return []

        embedding = self.embedder.embed(query) if self.embedder else None
        index_list = ",".join(indices)

        resp = None
        # 1. Best path: RRF hybrid (requires Platinum on self-hosted ES,
        #    free on Atlas Vector Search and Elastic Cloud).
        if embedding is not None:
            try:
                resp = self._es.search(
                    index=index_list,
                    body=self._rrf_body(query, embedding, limit),
                )
            except Exception as exc:
                # AuthorizationException on basic license, or any other error.
                # Fall through to kNN-only.
                logger.debug("RRF unavailable (%s); falling back to kNN-only", exc)

        # 2. Vector-only kNN (works on basic license).
        if resp is None and embedding is not None:
            try:
                resp = self._es.search(
                    index=index_list,
                    body=self._knn_body(embedding, limit),
                )
            except Exception as exc:
                logger.debug("kNN failed (%s); falling back to BM25", exc)

        # 3. Last resort: BM25 keyword only.
        if resp is None:
            try:
                resp = self._es.search(
                    index=index_list,
                    body=self._bm25_body(query, limit),
                )
            except Exception as exc:
                logger.warning("hybrid_search BM25 fallback failed: %s", exc)
                return []

        hits = (resp.get("hits") or {}).get("hits") or []
        out: list[dict] = []
        for h in hits:
            src = h.get("_source") or {}
            out.append({
                "index": h.get("_index"),
                "score": h.get("_score") or 0.0,
                "title": src.get("title"),
                "snippet": src.get("description") or src.get("content") or "",
                "url": src.get("web_url") or src.get("source_path"),
                "state": src.get("state"),
                "labels": src.get("labels"),
                "updated_at": src.get("updated_at"),
            })
        return out

    # ── Query body builders ──────────────────────────────────────────────────

    @staticmethod
    def _rrf_body(query: str, embedding: list[float], limit: int) -> dict:
        """Hybrid BM25 + kNN via Reciprocal Rank Fusion (Platinum / Cloud)."""
        return {
            "size": limit,
            "retriever": {
                "rrf": {
                    "retrievers": [
                        {
                            "standard": {
                                "query": {
                                    "multi_match": {
                                        "query": query,
                                        "fields": ["title^3", "description", "content", "labels"],
                                    }
                                }
                            }
                        },
                        {
                            "knn": {
                                "field": "embedding",
                                "query_vector": embedding,
                                "k": max(limit * 2, 10),
                                "num_candidates": max(50, limit * 10),
                            }
                        },
                    ],
                    "rank_window_size": max(50, limit * 10),
                    "rank_constant": 60,
                }
            },
            "_source": {"excludes": ["embedding"]},
        }

    @staticmethod
    def _knn_body(embedding: list[float], limit: int) -> dict:
        """Vector-only kNN — works on basic ES license."""
        return {
            "size": limit,
            "knn": {
                "field": "embedding",
                "query_vector": embedding,
                "k": max(limit * 2, 10),
                "num_candidates": max(50, limit * 10),
            },
            "_source": {"excludes": ["embedding"]},
        }

    @staticmethod
    def _bm25_body(query: str, limit: int) -> dict:
        """Keyword-only BM25 fallback when no embedding is available."""
        return {
            "size": limit,
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "description", "content", "labels"],
                }
            },
            "_source": {"excludes": ["embedding"]},
        }

    # ── ES|QL ────────────────────────────────────────────────────────────────

    def run_esql(self, query: str, *, max_rows: int = 200) -> dict:
        """Execute a raw ES|QL query. Returns ``{columns, rows, truncated}``.

        The agent gets read-only access. Writes via ES|QL DELETE/UPDATE
        are not currently supported by ES|QL anyway; if Elastic adds them
        later we'll filter here.
        """
        if not self.connected:
            return {"error": "Elastic not connected", "columns": [], "rows": []}
        if not query or not query.strip():
            return {"error": "empty query", "columns": [], "rows": []}
        try:
            resp = self._es.esql.query(query=query, format="json")
            cols = resp.get("columns") or []
            rows = resp.get("values") or []
            truncated = False
            if len(rows) > max_rows:
                rows = rows[:max_rows]
                truncated = True
            return {
                "columns": [{"name": c.get("name"), "type": c.get("type")} for c in cols],
                "rows": rows,
                "truncated": truncated,
            }
        except Exception as exc:
            logger.warning("run_esql failed: %s", exc)
            return {"error": str(exc), "columns": [], "rows": []}

    # ── Bulk helpers (used by ingest scripts, not by the agent) ──────────────

    def bulk_index(self, index: str, docs: list[dict]) -> int:
        """Index a batch of docs. Each doc may include ``_id``. Returns count."""
        if not self.connected or not docs:
            return 0
        try:
            from elasticsearch.helpers import bulk
        except ImportError:
            return 0
        actions = []
        for d in docs:
            source = {k: v for k, v in d.items() if k != "_id"}
            action: dict[str, Any] = {"_index": index, "_source": source}
            if d.get("_id") is not None:
                action["_id"] = d["_id"]
            actions.append(action)
        try:
            success, _errs = bulk(self._es, actions, raise_on_error=False)
            return int(success)
        except Exception as exc:
            logger.warning("bulk_index failed: %s", exc)
            return 0
