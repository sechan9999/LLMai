import json
from typing import Iterator
import requests


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2.5-coder"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._url = f"{self.base_url}/v1/chat/completions"

    # ── Non-streaming: returns full assistant message dict ──────────────────
    def chat(self, messages: list[dict], tools: list[dict] = None, timeout: int = 120) -> dict:
        payload = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        resp = requests.post(self._url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]

    # ── Streaming: yields text chunks (text-only, no tool calls) ────────────
    def stream(self, messages: list[dict], timeout: int = 120) -> Iterator[str]:
        payload = {"model": self.model, "messages": messages, "stream": True}
        with requests.post(self._url, json=payload, stream=True, timeout=timeout) as resp:
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

    def is_available(self) -> bool:
        try:
            requests.get(f"{self.base_url}/api/tags", timeout=3)
            return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return []
