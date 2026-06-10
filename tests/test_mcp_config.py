"""Unit tests for MCP config parsing and the init() gate — no SDK required."""
import llmai.mcp as mcp_layer
from llmai.mcp.client import parse_servers_config


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
