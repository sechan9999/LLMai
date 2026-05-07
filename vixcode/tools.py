import subprocess
import re
from pathlib import Path
from typing import Any


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
                    "limit": {"type": "integer", "description": "Number of lines to read"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file, creating it if it doesn't exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace an exact unique string in a file. old_string must be unique.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string", "description": "Exact text to find (must be unique in file)"},
                    "new_string": {"type": "string", "description": "Text to replace it with"}
                },
                "required": ["path", "old_string", "new_string"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Execute a shell command. Use for git, tests, package managers, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "description": "Seconds before timeout (default: 30)"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory, with optional glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "pattern": {"type": "string", "description": "Glob pattern e.g. '**/*.py'"}
                },
                "required": ["path"]
            }
        }
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
                    "path": {"type": "string"},
                    "include": {"type": "string", "description": "File pattern e.g. '*.py'"}
                },
                "required": ["pattern", "path"]
            }
        }
    },
]


def execute_tool(name: str, args: dict[str, Any]) -> str:
    handlers = {
        "read_file": _read_file,
        "write_file": _write_file,
        "edit_file": _edit_file,
        "run_bash": _run_bash,
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
    except Exception as e:
        return f"Error in {name}: {e}"


def _read_file(path: str, offset: int = None, limit: int = None) -> str:
    p = Path(path)
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
        header += f", showing {start+1}–{min(end, len(lines))}"
    return f"{header})\n\n{numbered}"


def _write_file(path: str, content: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content.splitlines())} lines to {path}"


def _edit_file(path: str, old_string: str, new_string: str) -> str:
    p = Path(path)
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


def _run_bash(command: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
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
    p = Path(path)
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
    # Try system grep first
    cmd = ["grep", "-rn", "--color=never", pattern, path]
    if include:
        cmd += ["--include", include]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, encoding="utf-8")
        output = result.stdout.strip()
        if not output:
            return f"No matches for '{pattern}' in {path}"
        lines = output.splitlines()
        truncated = "\n".join(lines[:100])
        if len(lines) > 100:
            truncated += f"\n... ({len(lines) - 100} more matches)"
        return truncated
    except FileNotFoundError:
        pass

    # Fallback: pure Python
    p = Path(path)
    results = []
    files = list(p.rglob(include or "*")) if p.is_dir() else [p]
    for f in files:
        if not f.is_file():
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if re.search(pattern, line):
                    results.append(f"{f}:{i}: {line}")
                    if len(results) >= 100:
                        return "\n".join(results)
        except Exception:
            continue
    return "\n".join(results) if results else f"No matches for '{pattern}' in {path}"
