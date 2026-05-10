"""
OllamaClient — HTTP client for Ollama's OpenAI-compatible API.

Supports both non-streaming (tool calls) and streaming (text-only) modes.
"""
import json
import logging
import time
from typing import Iterator

import requests

logger = logging.getLogger(__name__)


def _is_transient(exc: Exception) -> bool:
    """Return True if *exc* is a network error worth retrying."""
    return isinstance(
        exc,
        (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError),
    )


class OllamaClient:
    """Lightweight HTTP client for the Ollama /v1/chat/completions endpoint.

    Attributes:
        base_url: Ollama server URL (default: http://localhost:11434).
        model: Active model name (can be changed at runtime).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._url = f"{self.base_url}/v1/chat/completions"

    # ── Non-streaming: returns full assistant message dict ──────────────────

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        timeout: int = 120,
        *,
        retries: int = 2,
    ) -> dict:
        """Send a chat completion request and return the assistant message.

        Retries up to *retries* times on transient network errors with
        exponential backoff (0.5s, 1s).

        Args:
            messages: Conversation history in OpenAI format.
            tools: Optional list of tool definitions.
            timeout: Request timeout in seconds.
            retries: Max retry attempts on transient errors.

        Returns:
            The ``choices[0].message`` dict from the API response.

        Raises:
            requests.HTTPError: On non-2xx responses.
            requests.ConnectionError / Timeout: After exhausting retries.
        """
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        backoff = 0.5
        for attempt in range(retries + 1):
            try:
                resp = requests.post(self._url, json=payload, timeout=timeout)
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as exc:
                if attempt < retries and _is_transient(exc):
                    logger.warning(
                        "Ollama request failed (attempt %d/%d): %s — retrying in %.1fs",
                        attempt + 1, retries + 1, exc, backoff,
                    )
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise

        # P3: Capture token usage when available
        usage = data.get("usage")
        if usage:
            logger.debug(
                "Token usage — prompt: %d, completion: %d, total: %d",
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                usage.get("total_tokens", 0),
            )

        return data["choices"][0]["message"]

    # ── Streaming: yields text chunks (text-only, no tool calls) ────────────

    def stream(self, messages: list[dict], timeout: int = 120) -> Iterator[str]:
        """Stream a chat completion, yielding text chunks as they arrive.

        This mode does NOT support tool calls — use :meth:`chat` for that.

        Args:
            messages: Conversation history.
            timeout: Request timeout in seconds.

        Yields:
            Text content chunks from the assistant.
        """
        payload = {"model": self.model, "messages": messages, "stream": True}
        with requests.post(
            self._url, json=payload, stream=True, timeout=timeout
        ) as resp:
            resp.raise_for_status()
            buf = ""
            for raw in resp.iter_content(chunk_size=None, decode_unicode=True):
                buf += raw
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            chunk = data["choices"][0]["delta"].get("content", "")
                            if chunk:
                                yield chunk
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

    # ── Utilities ─────────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Check whether the Ollama server is reachable and healthy."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            resp.raise_for_status()
            return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Return names of locally available models."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return []
