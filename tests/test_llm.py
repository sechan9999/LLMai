"""Tests for vixcode.llm — OllamaClient with mocked HTTP."""
from unittest.mock import MagicMock, patch

import pytest

from vixcode.llm import OllamaClient


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
