import json
from pathlib import Path
from typing import Literal

PermMode = Literal["allow", "ask", "deny"]

# Safe read-only ops: auto-allow. Writes & shell: ask.
DEFAULT: dict[str, PermMode] = {
    "read_file":   "allow",
    "list_files":  "allow",
    "search_code": "allow",
    "write_file":  "ask",
    "edit_file":   "ask",
    "run_bash":    "ask",
}


class PermissionManager:
    def __init__(self, config_path: str = None):
        self.rules: dict[str, PermMode] = dict(DEFAULT)
        if config_path:
            p = Path(config_path)
            if p.exists():
                data = json.loads(p.read_text())
                self.rules.update(data.get("permissions", {}))

    def check(self, tool_name: str, args: dict) -> bool:
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

    def set_mode(self, tool_name: str, mode: PermMode):
        self.rules[tool_name] = mode


def _preview(name: str, args: dict) -> str:
    if name == "run_bash":
        cmd = args.get("command", "")
        return f"run_bash: `{cmd[:80]}`"
    if name == "write_file":
        return f"write_file: {args.get('path', '')}"
    if name == "edit_file":
        old = args.get("old_string", "")[:40]
        return f"edit_file: {args.get('path', '')}  (replace '{old}...')"
    parts = [f"{k}={repr(v)[:30]}" for k, v in args.items()]
    return f"{name}({', '.join(parts)})"
