"""Unit tests for MCP config parsing and the init() gate — no SDK required."""
import pytest

import llmai.mcp as mcp_layer
from llmai import tools as _vt
from llmai.mcp.client import parse_servers_config
from llmai.mcp.registry import McpRegistry


class TestParseServersConfig:
    def test_valid_entry(self):
        cfgs = parse_servers_config({
            "mongodb": {
                "command": "npx",
                "args": ["-y", "mongodb-mcp-server"],
                "env": {"FOO": "bar"},
                "allow": ["find"],
            }
        })
        assert len(cfgs) == 1
        c = cfgs[0]
        assert c.name == "mongodb"
        assert c.command == "npx"
        assert c.args == ["-y", "mongodb-mcp-server"]
        assert c.allow == ["find"]

    def test_missing_command_skipped(self):
        cfgs = parse_servers_config({"bad": {"args": ["x"]}, "good": {"command": "py"}})
        assert [c.name for c in cfgs] == ["good"]

    def test_non_dict_entry_skipped(self):
        assert parse_servers_config({"bad": "just-a-string"}) == []

    def test_env_expansion(self, monkeypatch):
        monkeypatch.setenv("MY_SECRET", "s3cret")
        cfgs = parse_servers_config({
            "s": {"command": "c", "env": {"TOKEN": "${MY_SECRET}", "MIX": "pre-${MY_SECRET}"}}
        })
        assert cfgs[0].env == {"TOKEN": "s3cret", "MIX": "pre-s3cret"}

    def test_unset_env_var_becomes_empty(self, monkeypatch):
        monkeypatch.delenv("DEFINITELY_NOT_SET_123", raising=False)
        cfgs = parse_servers_config({
            "s": {"command": "c", "env": {"TOKEN": "${DEFINITELY_NOT_SET_123}"}}
        })
        assert cfgs[0].env == {"TOKEN": ""}

    def test_empty_block(self):
        assert parse_servers_config({}) == []
        assert parse_servers_config(None) == []


class TestInitGate:
    def teardown_method(self):
        mcp_layer.shutdown()

    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("LLMAI_MCP_ENABLED", raising=False)
        assert mcp_layer.init({}) is False
        assert mcp_layer.is_enabled() is False

    def test_env_false_overrides_config_true(self, monkeypatch):
        monkeypatch.setenv("LLMAI_MCP_ENABLED", "false")
        assert mcp_layer.init({"enabled": True, "servers": {"s": {"command": "x"}}}) is False

    def test_enabled_but_no_servers(self, monkeypatch):
        monkeypatch.setenv("LLMAI_MCP_ENABLED", "true")
        assert mcp_layer.init({"servers": {}}) is False
        assert mcp_layer.is_enabled() is False

    def test_get_registrations_empty_when_disabled(self):
        assert mcp_layer.get_registrations() == []

    def test_shutdown_idempotent(self):
        mcp_layer.shutdown()
        mcp_layer.shutdown()
        assert mcp_layer.is_enabled() is False

    def test_nonexistent_command_yields_failed_state(self, monkeypatch):
        # GAP-3: bad server command -> 'failed' state, agent unaffected.
        pytest.importorskip("mcp", reason="requires the [mcp] extra")
        monkeypatch.setenv("LLMAI_MCP_ENABLED", "true")
        ok = mcp_layer.init({
            "servers": {"broken": {"command": "definitely-not-a-command-xyz"}}
        })
        assert ok is False
        assert mcp_layer.is_enabled() is False
        [state] = mcp_layer.get_server_states()
        assert state.status == "failed"
        assert state.error


class TestSubprocessEnv:
    def test_parent_secrets_not_inherited(self, monkeypatch):
        # GAP-1 regression: only named vars + SDK-safe defaults are passed.
        pytest.importorskip("mcp", reason="requires the [mcp] extra")
        from llmai.mcp.client import build_subprocess_env
        monkeypatch.setenv("SUPER_SECRET_API_KEY", "leak-me-not")
        env = build_subprocess_env({"WANTED": "yes"})
        assert "SUPER_SECRET_API_KEY" not in env
        assert env["WANTED"] == "yes"


class TestRegisterMcpToolsIdempotency:
    def test_double_registration_adds_once(self, monkeypatch):
        # GAP-3: register_mcp_tools() called twice must not duplicate.
        registry = McpRegistry(call_fn=lambda s, t, a: "ok")
        registry.add_server_tools("fake", [("ping", "test tool", {})])
        monkeypatch.setattr(mcp_layer, "is_enabled", lambda: True)
        monkeypatch.setattr(
            mcp_layer, "get_registrations", registry.get_registrations
        )
        before = len(_vt.TOOL_DEFINITIONS)
        try:
            _vt.register_mcp_tools()
            _vt.register_mcp_tools()
            names = [t["function"]["name"] for t in _vt.TOOL_DEFINITIONS]
            assert names.count("mcp__fake__ping") == 1
            assert len(_vt.TOOL_DEFINITIONS) == before + 1
        finally:
            _vt.TOOL_DEFINITIONS[:] = [
                t for t in _vt.TOOL_DEFINITIONS
                if t["function"]["name"] != "mcp__fake__ping"
            ]
            _vt._BASE_HANDLERS.pop("mcp__fake__ping", None)
