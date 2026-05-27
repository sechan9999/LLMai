"""Tests for llmai.permissions — permission modes and config loading."""
import json
from unittest.mock import patch

from llmai.permissions import DEFAULT, PermissionManager, _preview


class TestPermissionManager:
    def test_default_modes(self):
        pm = PermissionManager()
        assert pm.rules["read_file"] == "allow"
        assert pm.rules["list_files"] == "allow"
        assert pm.rules["search_code"] == "allow"
        assert pm.rules["write_file"] == "ask"
        assert pm.rules["edit_file"] == "ask"
        assert pm.rules["run_bash"] == "ask"
        assert pm.rules["run_command"] == "ask"

    def test_allow_mode_returns_true(self):
        pm = PermissionManager()
        assert pm.check("read_file", {"path": "test.txt"}) is True

    def test_deny_mode_returns_false(self):
        pm = PermissionManager()
        pm.set_mode("write_file", "deny")
        assert pm.check("write_file", {"path": "test.txt"}) is False

    def test_ask_mode_approved(self):
        pm = PermissionManager()
        with patch("builtins.input", return_value="y"):
            assert pm.check("write_file", {"path": "test.txt"}) is True

    def test_ask_mode_denied(self):
        pm = PermissionManager()
        with patch("builtins.input", return_value="n"):
            assert pm.check("write_file", {"path": "test.txt"}) is False

    def test_ask_mode_empty_input_denied(self):
        pm = PermissionManager()
        with patch("builtins.input", return_value=""):
            assert pm.check("write_file", {"path": "test.txt"}) is False

    def test_ask_mode_eof_denied(self):
        pm = PermissionManager()
        with patch("builtins.input", side_effect=EOFError):
            assert pm.check("write_file", {"path": "test.txt"}) is False

    def test_load_config(self, tmp_path):
        config = {"permissions": {"write_file": "allow", "run_bash": "deny"}}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config))

        pm = PermissionManager(config_path=str(config_file))
        assert pm.rules["write_file"] == "allow"
        assert pm.rules["run_bash"] == "deny"
        # Unchanged defaults preserved
        assert pm.rules["read_file"] == "allow"

    def test_load_bad_config_graceful(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("not valid json")
        # Should not raise
        pm = PermissionManager(config_path=str(config_file))
        assert pm.rules == dict(DEFAULT)

    def test_set_mode(self):
        pm = PermissionManager()
        pm.set_mode("read_file", "deny")
        assert pm.rules["read_file"] == "deny"

    def test_unknown_tool_defaults_to_ask(self):
        pm = PermissionManager()
        with patch("builtins.input", return_value="y"):
            assert pm.check("some_new_tool", {}) is True


class TestPreview:
    def test_run_bash_preview(self):
        result = _preview("run_bash", {"command": "echo hello"})
        assert "run_command" in result
        assert "echo hello" in result

    def test_run_command_preview(self):
        result = _preview("run_command", {"command": "ls -la"})
        assert "run_command" in result

    def test_write_file_preview(self):
        result = _preview("write_file", {"path": "/tmp/test.txt"})
        assert "write_file" in result
        assert "/tmp/test.txt" in result

    def test_edit_file_preview(self):
        result = _preview("edit_file", {
            "path": "foo.py",
            "old_string": "old text here",
        })
        assert "edit_file" in result
        assert "foo.py" in result

    def test_generic_preview(self):
        result = _preview("read_file", {"path": "test.py"})
        assert "read_file" in result
