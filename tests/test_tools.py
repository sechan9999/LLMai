"""Tests for llmai.tools — file, directory, and search operations."""
import os

import pytest

from llmai.tools import (
    WORKSPACE_ROOT,
    _is_dangerous_command,
    _validate_path,
    execute_tool,
    set_workspace,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def workspace(tmp_path):
    """Create a temporary workspace and set it as WORKSPACE_ROOT."""
    old_root = WORKSPACE_ROOT
    set_workspace(tmp_path)
    yield tmp_path
    set_workspace(old_root)


# ── Path validation ──────────────────────────────────────────────────────────

class TestValidatePath:
    def test_valid_path_inside_workspace(self, workspace):
        (workspace / "hello.txt").write_text("hi")
        result = _validate_path(str(workspace / "hello.txt"))
        assert result == workspace / "hello.txt"

    def test_rejects_path_outside_workspace(self, workspace):
        with pytest.raises(ValueError, match="outside the workspace"):
            _validate_path("/etc/passwd")

    def test_rejects_traversal_attack(self, workspace):
        with pytest.raises(ValueError, match="outside the workspace"):
            _validate_path(str(workspace / ".." / ".." / "etc" / "passwd"))


# ── Dangerous command detection ──────────────────────────────────────────────

class TestDangerousCommands:
    @pytest.mark.parametrize("cmd", [
        "rm -rf /",
        "rm -r /home",
        "mkfs.ext4 /dev/sda1",
        "shutdown -h now",
        "reboot",
        "dd if=/dev/zero of=/dev/sda",
    ])
    def test_dangerous_commands_detected(self, cmd):
        assert _is_dangerous_command(cmd) is True

    @pytest.mark.parametrize("cmd", [
        "ls -la",
        "git status",
        "python -m pytest",
        "rm temp_file.txt",
        "echo hello",
    ])
    def test_safe_commands_allowed(self, cmd):
        assert _is_dangerous_command(cmd) is False


# ── read_file ────────────────────────────────────────────────────────────────

class TestReadFile:
    def test_read_existing_file(self, workspace):
        f = workspace / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        result = execute_tool("read_file", {"path": str(f)})
        assert "3 lines total" in result
        assert "line1" in result
        assert "line2" in result

    def test_read_nonexistent_file(self, workspace):
        result = execute_tool("read_file", {"path": str(workspace / "nope.txt")})
        assert "Error" in result
        assert "not found" in result

    def test_read_with_offset_and_limit(self, workspace):
        f = workspace / "test.txt"
        f.write_text("\n".join(f"line{i}" for i in range(1, 11)))
        result = execute_tool("read_file", {"path": str(f), "offset": 3, "limit": 2})
        assert "line3" in result
        assert "line4" in result
        assert "line5" not in result

    def test_read_file_outside_workspace(self, workspace):
        result = execute_tool("read_file", {"path": "/etc/hosts"})
        assert "Error" in result


# ── write_file ───────────────────────────────────────────────────────────────

class TestWriteFile:
    def test_write_new_file(self, workspace):
        target = workspace / "output.txt"
        result = execute_tool("write_file", {"path": str(target), "content": "hello\nworld"})
        assert "Wrote 2 lines" in result
        assert target.read_text() == "hello\nworld"

    def test_write_creates_directories(self, workspace):
        target = workspace / "sub" / "dir" / "file.txt"
        result = execute_tool("write_file", {"path": str(target), "content": "nested"})
        assert "Wrote" in result
        assert target.exists()

    def test_write_outside_workspace(self, workspace):
        result = execute_tool("write_file", {"path": "/tmp/evil.txt", "content": "bad"})
        assert "Error" in result


# ── edit_file ────────────────────────────────────────────────────────────────

class TestEditFile:
    def test_edit_unique_string(self, workspace):
        f = workspace / "test.py"
        f.write_text("x = 1\ny = 2\n")
        result = execute_tool("edit_file", {
            "path": str(f),
            "old_string": "x = 1",
            "new_string": "x = 42",
        })
        assert "1 replacement" in result
        assert "x = 42" in f.read_text()

    def test_edit_nonunique_string(self, workspace):
        f = workspace / "test.py"
        f.write_text("x = 1\nx = 1\n")
        result = execute_tool("edit_file", {
            "path": str(f),
            "old_string": "x = 1",
            "new_string": "x = 42",
        })
        assert "appears 2 times" in result

    def test_edit_string_not_found(self, workspace):
        f = workspace / "test.py"
        f.write_text("x = 1\n")
        result = execute_tool("edit_file", {
            "path": str(f),
            "old_string": "not_here",
            "new_string": "replaced",
        })
        assert "not found" in result


# ── run_command ──────────────────────────────────────────────────────────────

class TestRunCommand:
    def test_simple_command(self, workspace):
        result = execute_tool("run_command", {"command": "echo hello"})
        assert "hello" in result

    def test_dangerous_command_blocked(self, workspace):
        result = execute_tool("run_command", {"command": "rm -rf /"})
        assert "blocked" in result.lower() or "dangerous" in result.lower()

    def test_legacy_run_bash_alias(self, workspace):
        result = execute_tool("run_bash", {"command": "echo legacy"})
        assert "legacy" in result

    def test_timeout(self, workspace):
        # Use a very short timeout with a sleep command
        if os.name == "nt":
            cmd = "Start-Sleep -Seconds 5"
        else:
            cmd = "sleep 5"
        result = execute_tool("run_command", {"command": cmd, "timeout": 1})
        assert "timed out" in result


# ── list_files ───────────────────────────────────────────────────────────────

class TestListFiles:
    def test_list_directory(self, workspace):
        (workspace / "a.txt").write_text("a")
        (workspace / "b.txt").write_text("b")
        result = execute_tool("list_files", {"path": str(workspace)})
        assert "a.txt" in result
        assert "b.txt" in result

    def test_list_with_glob(self, workspace):
        (workspace / "a.py").write_text("a")
        (workspace / "b.txt").write_text("b")
        result = execute_tool("list_files", {"path": str(workspace), "pattern": "*.py"})
        assert "a.py" in result
        assert "b.txt" not in result

    def test_list_nonexistent(self, workspace):
        result = execute_tool("list_files", {"path": str(workspace / "nope")})
        assert "Error" in result


# ── search_code ──────────────────────────────────────────────────────────────

class TestSearchCode:
    def test_search_finds_pattern(self, workspace):
        (workspace / "test.py").write_text("def hello():\n    return 42\n")
        result = execute_tool("search_code", {"pattern": "hello", "path": str(workspace)})
        assert "hello" in result

    def test_search_no_matches(self, workspace):
        (workspace / "test.py").write_text("x = 1\n")
        result = execute_tool(
            "search_code",
            {"pattern": "nonexistent_pattern", "path": str(workspace)},
        )
        assert "No matches" in result


# ── Unknown tool ─────────────────────────────────────────────────────────────

def test_unknown_tool():
    result = execute_tool("nonexistent_tool", {})
    assert "Unknown tool" in result
