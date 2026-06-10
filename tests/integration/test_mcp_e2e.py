"""
End-to-end MCP integration test against the Python stub server.

Needs the [mcp] extra installed but NO live backends and NO Node.js —
the stub speaks real MCP over stdio. Run with:

    pytest tests/integration/test_mcp_e2e.py -m integration
"""
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

pytest.importorskip("mcp", reason="requires: pip install 'llmai-agent[mcp]'")

import llmai.mcp as mcp_layer  # noqa: E402
from llmai import tools as _vt  # noqa: E402

STUB = Path(__file__).parent / "mcp_stub_server.py"


@pytest.fixture()
def mcp_enabled(monkeypatch):
    monkeypatch.setenv("LLMAI_MCP_ENABLED", "true")
    config = {
        "call_timeout_s": 15,
        "servers": {
            "stub": {
                "command": sys.executable,
                "args": [str(STUB)],
                "allow": ["echo"],
            }
        },
    }
    assert mcp_layer.init(config) is True
    yield
    # Remove registered tools so other tests see a clean registry.
    qualified = {spec.qualified for spec, _ in mcp_layer.get_registrations()}
    _vt.TOOL_DEFINITIONS[:] = [
        t for t in _vt.TOOL_DEFINITIONS if t["function"]["name"] not in qualified
    ]
    for name in qualified:
        _vt._BASE_HANDLERS.pop(name, None)
    mcp_layer.shutdown()


class TestMcpEndToEnd:
    def test_discovery_and_states(self, mcp_enabled):
        assert mcp_layer.is_enabled()
        [state] = mcp_layer.get_server_states()
        assert state.status == "connected"
        names = {spec.qualified for spec, _ in mcp_layer.get_registrations()}
        assert names == {"mcp__stub__echo", "mcp__stub__add"}

    def test_permission_defaults(self, mcp_enabled):
        perms = mcp_layer.MCP_DEFAULT_PERMISSIONS
        assert perms["mcp__stub__echo"] == "allow"   # in the allow list
        assert perms["mcp__stub__add"] == "ask"      # not listed -> ask

    def test_register_and_execute_through_dispatcher(self, mcp_enabled):
        _vt.register_mcp_tools()
        tool_names = {t["function"]["name"] for t in _vt.TOOL_DEFINITIONS}
        assert "mcp__stub__echo" in tool_names

        result = _vt.execute_tool("mcp__stub__echo", {"text": "hello mcp"})
        assert result == "echo: hello mcp"

        result = _vt.execute_tool("mcp__stub__add", {"a": 2, "b": 40})
        assert "42" in result

    def test_call_after_shutdown_degrades(self, mcp_enabled):
        _vt.register_mcp_tools()
        handler = _vt._BASE_HANDLERS["mcp__stub__echo"]
        mcp_layer.shutdown()
        out = handler(text="x")
        assert out.startswith("Error:")
