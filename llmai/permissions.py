"""
Permission management for llmai tool execution.

Each tool can be in one of three modes:
  - allow : auto-approve (default for read-only tools)
  - ask   : prompt user before execution (default for writes & shell)
  - deny  : always block

Permissions are loaded from config files and can be changed at runtime.
"""
import json
import logging
from pathlib import Path
from typing import Literal

from .gitlab_tools import GITLAB_DEFAULT_PERMISSIONS

logger = logging.getLogger(__name__)

PermMode = Literal["allow", "ask", "deny"]

# Safe read-only ops: auto-allow.  Writes & shell: ask.
DEFAULT: dict[str, PermMode] = {
    "read_file":   "allow",
    "list_files":  "allow",
    "search_code": "allow",
    "write_file":  "ask",
    "edit_file":   "ask",
    "run_bash":    "ask",
    "run_command": "ask",
    # GitLab tools (active only when GITLAB_TOKEN is set; harmless otherwise)
    **GITLAB_DEFAULT_PERMISSIONS,
}


class PermissionManager:
    """Manages per-tool permission modes.

    Modes can be loaded from a JSON config file and overridden at runtime.
    """

    def __init__(self, config_path: str = None):
        self.rules: dict[str, PermMode] = dict(DEFAULT)
        if config_path:
            p = Path(config_path)
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    self.rules.update(data.get("permissions", {}))
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("Failed to load permissions from %s: %s", config_path, e)

    def check(self, tool_name: str, args: dict) -> bool:
        """Check whether *tool_name* is permitted.

        Returns True if the tool should execute, False otherwise.
        For mode='ask', prompts the user interactively.
        """
        mode = self.rules.get(tool_name, "ask")

        if mode == "allow":
            return True

        if mode == "deny":
            print(f"  [denied] {tool_name}")
            return False

        # ask
        preview = _preview(tool_name, args)
        try:
            answer = input(f"\n  Allow {preview}? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return answer in ("y", "yes")

    def set_mode(self, tool_name: str, mode: PermMode) -> None:
        """Override the permission mode for a specific tool."""
        self.rules[tool_name] = mode


def _preview(name: str, args: dict) -> str:
    """Build a human-readable preview string for a tool invocation.

    Used both in the CLI prompt and in the WebSocket permission card.
    """
    if name in ("run_bash", "run_command"):
        cmd = args.get("command", "")
        return f"run_command: `{cmd[:80]}`"
    if name == "write_file":
        return f"write_file: {args.get('path', '')}"
    if name == "edit_file":
        old = args.get("old_string", "")[:40]
        return f"edit_file: {args.get('path', '')}  (replace '{old}...')"
    if name == "gitlab_create_issue":
        return f"gitlab_create_issue: '{args.get('title', '')[:60]}'"
    if name == "gitlab_create_mr":
        return (
            f"gitlab_create_mr: '{args.get('title', '')[:50]}' "
            f"({args.get('source_branch', '')} → {args.get('target_branch', '')})"
        )
    if name in ("gitlab_comment_issue", "gitlab_comment_mr"):
        kind = "issue" if "issue" in name else "MR"
        body = args.get("body", "")[:60]
        return f"{name}: comment on {kind} #{args.get('iid')} — '{body}'"
    parts = [f"{k}={repr(v)[:30]}" for k, v in args.items()]
    return f"{name}({', '.join(parts)})"
