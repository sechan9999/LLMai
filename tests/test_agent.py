"""Tests for vixcode.agent — AgentLoop behavior with mocked LLM."""
import json
from unittest.mock import MagicMock, patch

import pytest

from vixcode.agent import AgentLoop, _fmt_args, _parse_tool_call
from vixcode.llm import OllamaClient
from vixcode.permissions import PermissionManager


@pytest.fixture()
def mock_llm():
    """Create a mock OllamaClient."""
    llm = MagicMock(spec=OllamaClient)
    llm.model = "test-model"
    return llm


@pytest.fixture()
def agent(mock_llm):
    """Create an AgentLoop with mock LLM and permissive permissions."""
    pm = PermissionManager()
    # Allow everything for testing
    for tool in pm.rules:
        pm.set_mode(tool, "allow")
    return AgentLoop(llm=mock_llm, permissions=pm)


class TestAgentLoop:
    def test_simple_text_response(self, agent, mock_llm):
        mock_llm.chat.return_value = {"content": "Hello!", "tool_calls": None}
        output = []
        result = agent.run("Hi", print_fn=output.append)
        assert result == "Hello!"
        assert any("Hello!" in str(o) for o in output)

    def test_context_starts_with_system_prompt(self, agent):
        assert len(agent.messages) == 1
        assert agent.messages[0]["role"] == "system"

    def test_reset_clears_context(self, agent, mock_llm):
        mock_llm.chat.return_value = {"content": "response", "tool_calls": None}
        agent.run("test")
        assert len(agent.messages) > 1
        agent.reset()
        assert len(agent.messages) == 1
        assert agent.messages[0]["role"] == "system"

    def test_token_estimate(self, agent):
        agent.messages.append({"role": "user", "content": "a" * 400})
        # 400 chars / 4 ≈ 100 tokens (plus system prompt)
        assert agent.token_estimate > 100

    def test_llm_error_handled(self, agent, mock_llm):
        mock_llm.chat.side_effect = ConnectionError("Ollama down")
        output = []
        agent.run("test", print_fn=output.append)
        assert any("error" in str(o).lower() for o in output)

    def test_max_iterations_cap(self, agent, mock_llm):
        # LLM always returns tool calls — should stop after max_iterations
        agent.max_iterations = 3
        mock_llm.chat.return_value = {
            "content": "",
            "tool_calls": [{
                "id": "1",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "test.txt"}),
                },
            }],
        }
        with patch("vixcode.agent.execute_tool", return_value="file content"):
            agent.run("loop test", print_fn=lambda *a: None)
        # Should have called chat exactly max_iterations times
        assert mock_llm.chat.call_count == 3


class TestParseToolCall:
    def test_parse_string_arguments(self):
        tc = {
            "id": "call_123",
            "function": {
                "name": "read_file",
                "arguments": '{"path": "test.txt"}',
            },
        }
        name, args, tc_id = _parse_tool_call(tc)
        assert name == "read_file"
        assert args == {"path": "test.txt"}
        assert tc_id == "call_123"

    def test_parse_dict_arguments(self):
        tc = {
            "id": "call_456",
            "function": {
                "name": "write_file",
                "arguments": {"path": "out.txt", "content": "hello"},
            },
        }
        name, args, tc_id = _parse_tool_call(tc)
        assert name == "write_file"
        assert args == {"path": "out.txt", "content": "hello"}

    def test_parse_invalid_json_arguments(self):
        tc = {
            "id": "call_789",
            "function": {
                "name": "edit_file",
                "arguments": "not-valid-json",
            },
        }
        name, args, tc_id = _parse_tool_call(tc)
        assert name == "edit_file"
        assert args == {}

    def test_parse_missing_fields(self):
        tc = {}
        name, args, tc_id = _parse_tool_call(tc)
        assert name == "unknown"
        assert args == {}
        assert tc_id == ""


class TestFmtArgs:
    def test_format_short_args(self):
        result = _fmt_args({"path": "test.txt", "offset": 5})
        assert "path='test.txt'" in result
        assert "offset=5" in result

    def test_format_truncates_long_values(self):
        long_value = "x" * 100
        result = _fmt_args({"content": long_value})
        assert "…" in result

    def test_format_empty_args(self):
        result = _fmt_args({})
        assert result == ""
