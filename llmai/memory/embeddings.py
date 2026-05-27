"""
Local embedding client — wraps Ollama's /api/embeddings endpoint.

Defaults to ``nomic-embed-text`` (768-dim). If the embed model isn't
available or the request fails, returns ``None`` — callers should store
records without embeddings rather than crashing. Such records won't be
vector-searchable but remain reachable by session_id / workspace_id.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from .._retry import with_retry

logger = logging.getLogger(__name__)


# Transient errors worth retrying — connection refused / timeout / temporary
# DNS failure. We do NOT retry on 4xx (model not found etc) — that's
# permanent and resp.raise_for_status() raises HTTPError, which we exclude.
_TRANSIENT = (
    requests.ConnectionError,
    requests.Timeout,
    requests.exceptions.ChunkedEncodingError,
)

EMBED_DIM = 768  # nomic-embed-text default


class Embedder:
    """Thin wrapper around an Ollama-compatible embeddings endpoint."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        timeout: int = 15,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._url = f"{self.base_url}/api/embeddings"
        self._warned_unavailable = False

    def embed(self, text: str) -> Optional[list[float]]:
        """Return a vector embedding for *text*, or None on failure.

        Transient HTTP failures retry up to 3 times with exponential backoff.
        Permanent failures (4xx, malformed response) are logged once per
        process and swallowed so a degraded embed service doesn't spam.
        """
        if not text or not text.strip():
            return None
        try:
            data = self._post_with_retry(text[:8000])
        except Exception as exc:
            if not self._warned_unavailable:
                logger.warning(
                    "Embedding endpoint unreachable (model=%s): %s. "
                    "Records will be stored without embeddings. "
                    "Pull the model: ollama pull %s",
                    self.model, exc, self.model,
                )
                self._warned_unavailable = True
            return None

        emb = data.get("embedding")
        if not isinstance(emb, list) or not emb:
            return None
        return [float(x) for x in emb]

    @with_retry(attempts=3, initial_delay=0.5, max_delay=3.0,
                retry_on=_TRANSIENT, label="ollama-embed")
    def _post_with_retry(self, text: str) -> dict:
        resp = requests.post(
            self._url,
            json={"model": self.model, "prompt": text},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()
