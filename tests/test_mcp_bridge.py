"""Unit tests for the MCP bridge sync facade — no MCP SDK required.

Fake connections are injected directly into the bridge; the real SDK
path is covered by tests/integration/test_mcp_e2e.py.
"""
import asyncio
from types import SimpleNamespace

from llmai.mcp.bridge import McpBridge
from llmai.mcp.client import McpServerConfig


class _FakeConn:
    """Duck-typed McpServerConnection."""

    def __init__(self, name="srv", connected=True, behavior="ok"):
        self.config = McpServerConfig(name=name, command="definitely-not-a-command-xyz")
        self.connected = connected
        self.behavior = behavior

    async def call(self, tool, args, timeout_s):
        if self.behavior == "ok":
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=f"{tool}:{args}")],
                isError=False,
            )
        if self.behavior == "timeout":
            raise asyncio.TimeoutError()
        if self.behavior == "dead":
            raise ConnectionError("pipe closed")
        raise RuntimeError("unexpected failure")

    async def stop(self):
        self.connected = False


class TestBridgeLifecycle:
    def test_call_before_start(self):
        bridge = McpBridge()
        out = bridge.call("srv", "tool", {})
        assert "not running" in out

    def test_start_stop_idempotent(self):
        bridge = McpBridge()
        bridge.start()
        bridge.start()
        bridge.stop()
        bridge.stop()

    def test_connect_before_start(self):
        bridge = McpBridge()
        ok, msg = bridge.connect(McpServerConfig(name="s", command="x"))
        assert ok is False
        assert "not started" in msg


class TestBridgeCalls:
    def setup_method(self):
        self.bridge = McpBridge(call_timeout_s=2.0)
        self.bridge.start()

    def teardown_method(self):
        self.bridge.stop()

    def test_unknown_server(self):
        assert "Unknown MCP server" in self.bridge.call("nope", "t", {})

    def test_successful_call_flattened(self):
        self.bridge._connections["srv"] = _FakeConn()
        out = self.bridge.call("srv", "echo", {"a": 1})
        assert out == "echo:{'a': 1}"

    def test_timeout_returns_error_string(self):
        self.bridge._connections["srv"] = _FakeConn(behavior="timeout")
        out = self.bridge.call("srv", "slow", {})
        assert "timed out" in out

    def test_dead_server_reconnect_fails_gracefully(self):
        # behavior="dead" -> ConnectionError -> reconnect attempt with a
        # nonexistent command fails -> friendly error, no exception.
        self.bridge._connections["srv"] = _FakeConn(behavior="dead")
        out = self.bridge.call("srv", "t", {})
        assert out == "Error: MCP server 'srv' is not connected"

    def test_tool_level_exception_no_retry(self):
        self.bridge._connections["srv"] = _FakeConn(behavior="boom")
        out = self.bridge.call("srv", "t", {})
        assert out.startswith("Error: mcp__srv__t failed: RuntimeError")
