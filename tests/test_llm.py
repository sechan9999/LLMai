"""Tests for vixcode.llm — OllamaClient with mocked HTTP."""
from unittest.mock import MagicMock, patch

import pytest

from vixcode.llm import OllamaClient, make_default_client, resolve_provider_config


@pytest.fixture()
def client():
    return OllamaClient(base_url="http://localhost:11434", model="test-model")


class TestOllamaClient:
    def test_init_url(self, client):
        assert client._url == "http://localhost:11434/v1/chat/completions"

    def test_init_strips_trailing_slash(self):
        c = OllamaClient(base_url="http://localhost:11434/")
        assert c.base_url == "http://localhost:11434"

    @patch("vixcode.llm.requests.post")
    def test_chat_returns_message(self, mock_post, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello!", "role": "assistant"}}],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = client.chat([{"role": "user", "content": "Hi"}])
        assert result["content"] == "Hello!"
        mock_post.assert_called_once()

    @patch("vixcode.llm.requests.post")
    def test_chat_includes_tools_when_provided(self, mock_post, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        tools = [{"type": "function", "function": {"name": "test"}}]
        client.chat([{"role": "user", "content": "test"}], tools=tools)

        call_args = mock_post.call_args
        payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
        assert "tools" in payload

    @patch("vixcode.llm.requests.post")
    def test_chat_no_tools_by_default(self, mock_post, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client.chat([{"role": "user", "content": "test"}])

        call_args = mock_post.call_args
        payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
        assert "tools" not in payload

    @patch("vixcode.llm.requests.get")
    def test_is_available_true(self, mock_get, client):
        mock_get.return_value = MagicMock()
        assert client.is_available() is True

    @patch("vixcode.llm.requests.get")
    def test_is_available_false(self, mock_get, client):
        mock_get.side_effect = ConnectionError()
        assert client.is_available() is False

    @patch("vixcode.llm.requests.get")
    def test_list_models(self, mock_get, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "models": [
                {"name": "qwen2.5-coder:7b"},
                {"name": "gemma3:4b"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        models = client.list_models()
        assert "qwen2.5-coder:7b" in models
        assert "gemma3:4b" in models

    @patch("vixcode.llm.requests.get")
    def test_list_models_error(self, mock_get, client):
        mock_get.side_effect = ConnectionError()
        assert client.list_models() == []

    def test_model_can_be_changed(self, client):
        client.model = "new-model"
        assert client.model == "new-model"


# ── Provider auto-detection ────────────────────────────────────────────────

class TestResolveProvider:
    def test_default_is_ollama(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_URL", raising=False)
        monkeypatch.delenv("VIXCODE_MODEL", raising=False)
        cfg = resolve_provider_config()
        assert cfg["provider"] == "ollama"
        assert cfg["base_url"] == "http://localhost:11434"
        assert cfg["chat_path"] == "/v1/chat/completions"
        assert cfg["headers"] == {}

    def test_gemini_when_api_key_set(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        cfg = resolve_provider_config()
        assert cfg["provider"] == "gemini"
        assert cfg["base_url"].endswith("/v1beta/openai")
        assert cfg["chat_path"] == "/chat/completions"
        assert cfg["headers"]["Authorization"] == "Bearer test-key"
        assert cfg["model"].startswith("gemini-")

    def test_gemini_model_override(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
        assert resolve_provider_config()["model"] == "gemini-2.5-pro"

    def test_explicit_base_url_takes_priority(self, monkeypatch):
        # Even with GEMINI_API_KEY set, an explicit base_url wins.
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        cfg = resolve_provider_config(base_url="http://my-proxy:8080")
        assert cfg["provider"] == "custom"
        assert cfg["base_url"] == "http://my-proxy:8080"


class TestMakeDefaultClient:
    def test_builds_ollama_client_by_default(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        c = make_default_client()
        assert c.provider == "ollama"
        assert c._url == "http://localhost:11434/v1/chat/completions"
        assert c.headers == {}

    def test_builds_gemini_client_with_auth_header(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "secret")
        c = make_default_client()
        assert c.provider == "gemini"
        assert c._url.endswith("/v1beta/openai/chat/completions")
        assert c.headers["Authorization"] == "Bearer secret"

    @patch("vixcode.llm.requests.post")
    def test_gemini_request_carries_auth_header(self, mock_post, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "abc")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": [{"message": {"content": "hi"}}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        c = make_default_client()
        c.chat([{"role": "user", "content": "test"}])

        sent_headers = mock_post.call_args.kwargs["headers"]
        assert sent_headers.get("Authorization") == "Bearer abc"

    def test_gemini_is_available_skips_probe(self, monkeypatch):
        # Cloud providers can't be probed via /api/tags — must trust config.
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        c = make_default_client()
        assert c.is_available() is True
