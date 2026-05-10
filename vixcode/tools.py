"""
Tool definitions and implementations for the vixcode agent.

Each tool is defined as an OpenAI-compatible function spec and paired
with a Python implementation.  The agent calls these via the LLM's
tool-calling mechanism.
"""
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Any

# ── Workspace sandbox ─────────────────────────────────────────────────────────
# All file operations are restricted to WORKSPACE_ROOT.
# Defaults to $VIXCODE_WORKSPACE if set, else the current working directory.

WORKSPACE_ROOT: Path = Path(
    os.environ.get("VIXCODE_WORKSPACE") or os.getcwd()
).resolve()


def set_workspace(path: str | Path) -> None:
    """Override the workspace root (used by tests and explicit launchers)."""
    global WORKSPACE_ROOT
    WORKSPACE_ROOT = Path(path).resolve()


# Common dirs that are always noise in code search.
_IGNORE_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "bower_components",
    ".venv", "venv", "env", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",
    "dist", "build", "out", ".next", ".nuxt",
    "target", ".gradle", ".idea", ".vscode",
})


def _validate_path(path: str) -> Path:
    """Resolve *path* and ensure it stays inside the workspace.

    Raises ValueError for any path-traversal attempt.
    """
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(WORKSPACE_ROOT)
    except ValueError:
        raise ValueError(
            f"Access denied: '{path}' resolves to '{resolved}' "
            f"which is outside the workspace '{WORKSPACE_ROOT}'"
        )
    return resolved


# ── Dangerous-command blocklist (P1 – shell injection guard) ──────────────────

_DANGEROUS_PATTERNS: list[str] = [
    r"rm\s+(-rf?|--recursive)\s+/",     # recursive delete from root
    r":()\{\s*:\|\s*:&\s*\};:",          # fork bomb
    r"mkfs\.",                            # format filesystem
    r"dd\s+if=.*/dev/",                  # raw disk write
    r">\s*/dev/sd",                       # redirect into raw device
    r"shutdown|reboot|halt|poweroff",     # system power commands
    r"chmod\s+-R\s+777\s+/",             # open permissions on root
]


def _is_dangerous_command(command: str) -> bool:
    """Return True if *command* matches a known destructive pattern."""
    for pat in _DANGEROUS_PATTERNS:
        if re.search(pat, command, re.IGNORECASE):
            return True
    return False


# ── Tool definitions (OpenAI function-calling format) ─────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file with line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file"},
                    "offset": {"type": "integer", "description": "Start from this line (1-based)"},
                    "limit": {"type": "integer", "description": "Number of lines to read"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file, creating it if it doesn't exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Destination file path"},
                    "content": {"type": "string", "description": "File content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace an exact unique string in a file. old_string must be unique.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File to edit"},
                    "old_string": {"type": "string", "description": "Exact text to find (must be unique in file)"},
                    "new_string": {"type": "string", "description": "Text to replace it with"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command. Use for git, tests, package managers, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {"type": "integer", "description": "Seconds before timeout (default: 30)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory, with optional glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to list"},
                    "pattern": {"type": "string", "description": "Glob pattern e.g. '**/*.py'"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search for text patterns in files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex or literal pattern"},
                    "path": {"type": "string", "description": "Directory or file to search"},
                    "include": {"type": "string", "description": "File pattern e.g. '*.py'"},
                },
                "required": ["pattern", "path"],
            },
        },
    },
]


# ── Dispatcher ────────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict[str, Any]) -> str:
    """Execute the named tool with the given arguments.

    Returns a human-readable string result or error message.
    """
    handlers = {
        "read_file": _read_file,
        "write_file": _write_file,
        "edit_file": _edit_file,
        "run_bash": _run_command,      # keep legacy alias
        "run_command": _run_command,
        "list_files": _list_files,
        "search_code": _search_code,
    }
    handler = handlers.get(name)
    if not handler:
        return f"Error: Unknown tool '{name}'"
    try:
        return handler(**args)
    except TypeError as e:
        return f"Error: Bad arguments for {name}: {e}"
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error in {name}: {e}"


# ── Tool implementations ─────────────────────────────────────────────────────

def _read_file(path: str, offset: int = None, limit: int = None) -> str:
    """Read file contents, returning numbered lines.

    Args:
        path: Absolute or relative file path.
        offset: 1-based starting line number.
        limit: Maximum number of lines to read.

    Returns:
        Formatted string with header and numbered lines.
    """
    p = _validate_path(path)
    if not p.exists():
        return f"Error: File not found: {path}"
    if not p.is_file():
        return f"Error: Not a file: {path}"
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return f"Error: Binary file (cannot read as text): {path}"

    start = (offset - 1) if offset and offset > 0 else 0
    end = (start + limit) if limit else len(lines)
    slice_ = lines[start:end]

    numbered = "\n".join(f"{start + i + 1:4d}  {line}" for i, line in enumerate(slice_))
    header = f"{path} ({len(lines)} lines total"
    if offset or limit:
        header += f", showing {start + 1}–{min(end, len(lines))}"
    return f"{header})\n\n{numbered}"


def _write_file(path: str, content: str) -> str:
    """Write *content* to *path*, creating parent directories as needed.

    Args:
        path: Destination file path.
        content: Text to write.

    Returns:
        Confirmation with line count.
    """
    p = _validate_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content.splitlines())} lines to {path}"


def _edit_file(path: str, old_string: str, new_string: str) -> str:
    """Replace a unique occurrence of *old_string* with *new_string*.

    Args:
        path: File to edit.
        old_string: Exact text to find (must appear exactly once).
        new_string: Replacement text.

    Returns:
        Confirmation or error if not found / not unique.
    """
    p = _validate_path(path)
    if not p.exists():
        return f"Error: File not found: {path}"
    content = p.read_text(encoding="utf-8")
    count = content.count(old_string)
    if count == 0:
        return f"Error: old_string not found in {path}"
    if count > 1:
        return f"Error: old_string appears {count} times; add more context to make it unique"
    p.write_text(content.replace(old_string, new_string, 1), encoding="utf-8")
    return f"Edited {path}: 1 replacement applied"


def _run_command(command: str, timeout: int = 30) -> str:
    """Execute a shell command with safety checks.

    On Windows, commands run through PowerShell for better compatibility.
    Dangerous command patterns are blocked before execution.

    Args:
        command: Shell command string.
        timeout: Maximum seconds before timeout (default 30).

    Returns:
        Combined stdout/stderr output with exit code on failure.
    """
    # P1: block obviously destructive commands
    if _is_dangerous_command(command):
        return "Error: Command blocked — matches a dangerous pattern. Please review."

    try:
        # P3: Windows compatibility — use PowerShell instead of cmd
        if platform.system() == "Windows":
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(WORKSPACE_ROOT),
                encoding="utf-8",
                errors="replace",
            )
        else:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(WORKSPACE_ROOT),
                encoding="utf-8",
                errors="replace",
            )
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"

    parts = []
    if result.stdout.strip():
        parts.append(result.stdout.strip())
    if result.stderr.strip():
        parts.append(f"[stderr]\n{result.stderr.strip()}")
    if result.returncode != 0:
        parts.append(f"[exit {result.returncode}]")
    return "\n".join(parts) or "(no output)"


def _list_files(path: str, pattern: str = None) -> str:
    """List directory contents with optional glob filtering.

    Args:
        path: Directory to list.
        pattern: Optional glob pattern (e.g. '**/*.py').

    Returns:
        Formatted directory listing, capped at 300 entries.
    """
    p = _validate_path(path)
    if not p.exists():
        return f"Error: Path not found: {path}"
    if not p.is_dir():
        return f"Error: Not a directory: {path}"

    matches = sorted(p.glob(pattern) if pattern else p.iterdir())
    if not matches:
        return f"(empty) {path}"

    lines = []
    for m in matches[:300]:
        rel = m.relative_to(p)
        lines.append(f"  {'/' if m.is_dir() else ' '} {rel}")
    result = f"{path}/\n" + "\n".join(lines)
    if len(matches) > 300:
        result += f"\n  ... {len(matches) - 300} more"
    return result


def _search_code(pattern: str, path: str, include: str = None) -> str:
    """Search for a text pattern in files.

    Uses system grep when available, otherwise falls back to pure Python.

    Args:
        pattern: Regex or literal search pattern.
        path: Directory or file to search.
        include: Optional file-name filter (e.g. '*.py').

    Returns:
        Matching lines with file/line info, capped at 100 results.
    """
    p = _validate_path(path)

    # Try system grep first (much faster for large codebases)
    cmd = ["grep", "-rn", "--color=never", pattern, str(p)]
    if include:
        cmd += ["--include", include]
    for d in _IGNORE_DIRS:
        cmd += ["--exclude-dir", d]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, encoding="utf-8"
        )
        output = result.stdout.strip()
        if not output:
            return f"No matches for '{pattern}' in {path}"
        lines = output.splitlines()
        truncated = "\n".join(lines[:100])
        if len(lines) > 100:
            truncated += f"\n... ({len(lines) - 100} more matches)"
        return truncated
    except FileNotFoundError:
        pass  # grep not available — fall through to Python impl

    # Fallback: pure Python regex search, skipping common ignored dirs.
    results = []
    if p.is_dir():
        files = (
            f for f in p.rglob(include or "*")
            if f.is_file() and not _IGNORE_DIRS.intersection(f.parts)
        )
    else:
        files = [p]
    for f in files:
        try:
            for i, line in enumerate(
                f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
            ):
                if re.search(pattern, line):
                    results.append(f"{f}:{i}: {line}")
                    if len(results) >= 100:
                        return "\n".join(results)
        except Exception:
            continue
    return "\n".join(results) if results else f"No matches for '{pattern}' in {path}"
