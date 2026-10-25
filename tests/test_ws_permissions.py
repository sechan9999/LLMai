"""Tests for the WebSocket approval gate in server.agent_ws."""
import asyncio
from unittest.mock import MagicMock

import pytest

from server.agent_ws import WebSocketAgent


@pytest.fixture()
def agent():
    """A WebSocketAgent whose outgoing messages are captured instead of sent."""
    a = WebSocketAgent("http://localhost:11434", "qwen2.5-coder", MagicMock())
    a.sent = []

    async def fake_send(msg_type, **kwargs):
        a.sent.append({"type": msg_type, **kwargs})

    a._send = fake_send
    return a


async def _answer_when_asked(agent, approved, *, wrong_id=False):
    """Wait for the permission card, then answer it like the UI would."""
    while not any(m["type"] == "permission_request" for m in agent.sent):
        await asyncio.sleep(0)
    rid = agent.sent[-1]["request_id"]
    await agent.handle_permission(approved, "not-" + rid if wrong_id else rid)


class TestPermissionGate:
    async def test_allow_mode_skips_card(self, agent):
        assert await agent._check_perm("read_file", {"path": "a.py"}) is True
        assert agent.sent == []

    async def test_deny_mode_skips_card(self, agent):
        agent.rules["write_file"] = "deny"
        assert await agent._check_perm("write_file", {"path": "a.py"}) is False
        assert agent.sent == []

    async def test_unknown_tool_asks(self, agent):
        task = asyncio.create_task(agent._check_perm("mcp__x__delete", {}))
        await _answer_when_asked(agent, True)
        assert await task is True
        assert agent.sent[0]["type"] == "permission_request"
        assert agent.sent[0]["request_id"]

    async def test_matching_response_approves(self, agent):
        task = asyncio.create_task(agent._check_perm("write_file", {"path": "a.py"}))
        await _answer_when_asked(agent, True)
        assert await task is True

    async def test_stale_approval_does_not_carry_over(self, agent):
        # A click left over from an earlier, cancelled card.
        await agent.handle_permission(True, "old-request")
        agent.PERMISSION_TIMEOUT_S = 0.05
        assert await agent._check_perm("run_command", {"command": "ls"}) is False
        assert agent.sent[-1]["type"] == "permission_expired"

    async def test_response_for_other_request_is_ignored(self, agent):
        agent.PERMISSION_TIMEOUT_S = 0.2
        task = asyncio.create_task(agent._check_perm("write_file", {"path": "a.py"}))
        await _answer_when_asked(agent, True, wrong_id=True)
        assert await task is False

    async def test_missing_request_id_is_ignored(self, agent):
        agent.PERMISSION_TIMEOUT_S = 0.05
        task = asyncio.create_task(agent._check_perm("write_file", {"path": "a.py"}))
        while not agent.sent:
            await asyncio.sleep(0)
        await agent.handle_permission(True)
        assert await task is False

    async def test_timeout_denies(self, agent):
        agent.PERMISSION_TIMEOUT_S = 0.05
        assert await agent._check_perm("write_file", {"path": "a.py"}) is False
        expired = agent.sent[-1]
        assert expired["type"] == "permission_expired"
        assert expired["request_id"] == agent.sent[0]["request_id"]

    @pytest.mark.parametrize("value", ["false", "true", 1, "yes", None])
    async def test_non_boolean_approval_denies(self, agent, value):
        task = asyncio.create_task(agent._check_perm("write_file", {"path": "a.py"}))
        await _answer_when_asked(agent, value)
        assert await task is False
