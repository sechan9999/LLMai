"""
OllamaClient — HTTP client for any OpenAI-compatible chat-completions API.

Speaks the same protocol as Ollama, Google Gemini (AI Studio + Vertex AI
OpenAI-compat), and other vendors that implement the OpenAI standard.
The class name is kept for stability — see :func:`make_default_client`
for the factory that picks a provider based on environment variables.
"""
import json
import logging
import os
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
    """Lightweight HTTP client for any OpenAI-compatible chat endpoint.

    Despite the name, the client works with Ollama, Google Gemini, or any
    other backend that implements the OpenAI ``/v1/chat/completions``
    contract. The class name is preserved for backwards compatibility.

    Attributes:
        base_url: Server URL (default: ``http://localhost:11434``).
        model: Active model name (can be changed at runtime).
        headers: Extra HTTP headers (e.g. ``Authorization: Bearer …``).
        provider: Free-form label for the active backend (Ollama, Gemini, …).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder",
        *,
        headers: dict[str, str] | None = None,
        chat_path: str = "/v1/chat/completions",
        provider: str = "ollama",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.headers: dict[str, str] = dict(headers or {})
        self.provider = provider
        self._url = f"{self.base_url}{chat_path}"

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
                resp = requests.post(
                    self._url, json=payload, timeout=timeout, headers=self.headers,
                )
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
            self._url, json=payload, stream=True, timeout=timeout, headers=self.headers,
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
        """Check whether the backend is reachable and healthy.

        Cloud providers like Gemini don't expose Ollama's ``/api/tags`` —
        for those, we just trust the configuration (the user explicitly
        supplied an API key) rather than probing.
        """
        if self.provider != "ollama":
            return True
        try:
            resp = requests.get(
                f"{self.base_url}/api/tags", timeout=3, headers=self.headers,
            )
            resp.raise_for_status()
            return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Return names of locally available models (Ollama only)."""
        if self.provider != "ollama":
            return [self.model] if self.model else []
        try:
            resp = requests.get(
                f"{self.base_url}/api/tags", timeout=5, headers=self.headers,
            )
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return []


# ── Provider auto-detection ──────────────────────────────────────────────────

# Google Gemini's OpenAI-compatible endpoint (AI Studio key path).
# For Vertex AI, point GEMINI_BASE_URL at the Vertex OpenAI compat endpoint
# and supply a bearer token from `gcloud auth print-access-token`.
_GEMINI_DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
_GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"


def resolve_provider_config(
    base_url: str | None = None,
    model: str | None = None,
) -> dict:
    """Pick an LLM backend based on environment + explicit overrides.

    Precedence:
      1. Explicit ``base_url`` argument (custom OpenAI-compat endpoint).
      2. ``GEMINI_API_KEY`` set → Google Gemini.
      3. Ollama on ``OLLAMA_URL`` (default ``http://localhost:11434``).
    """
    if base_url:
        return {
            "provider": "custom",
            "base_url": base_url.rstrip("/"),
            "chat_path": "/v1/chat/completions",
            "model": model or "qwen2.5-coder",
            "headers": {},
        }
    if os.environ.get("GEMINI_API_KEY"):
        return {
            "provider": "gemini",
            "base_url": os.environ.get("GEMINI_BASE_URL", _GEMINI_DEFAULT_BASE).rstrip("/"),
            "chat_path": "/chat/completions",
            "model": model or os.environ.get("GEMINI_MODEL", _GEMINI_DEFAULT_MODEL),
            "headers": {"Authorization": f"Bearer {os.environ['GEMINI_API_KEY']}"},
        }
    return {
        "provider": "ollama",
        "base_url": os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        "chat_path": "/v1/chat/completions",
        "model": model or os.environ.get("LLMAI_MODEL", "qwen2.5-coder"),
        "headers": {},
    }


def make_default_client(
    base_url: str | None = None,
    model: str | None = None,
) -> OllamaClient:
    """Construct an :class:`OllamaClient` aimed at the active provider."""
    cfg = resolve_provider_config(base_url, model)
    return OllamaClient(
        base_url=cfg["base_url"],
        model=cfg["model"],
        headers=cfg["headers"],
        chat_path=cfg["chat_path"],
        provider=cfg["provider"],
    )
