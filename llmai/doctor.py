"""
`llmai doctor` — pre-flight diagnostic.

Checks every dependency LLMai needs at runtime and reports green / yellow /
red status with actionable next steps. Read-only and side-effect-free
beyond a few HTTP HEAD/GET probes.

Exits with code 0 if every red check is fixable by the user (most are),
non-zero only on conditions LLMai cannot work around (e.g. wrong Python).
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import sys
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import requests

# ── ANSI colors with safe fallback ───────────────────────────────────────────

class _Color:
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        OK = WARN = BAD = DIM = RESET = ""
    else:
        OK = "\033[92m"
        WARN = "\033[93m"
        BAD = "\033[91m"
        DIM = "\033[90m"
        RESET = "\033[0m"


# Use Unicode glyphs only when stdout can encode them (Windows cp1252 can't).
def _supports_unicode() -> bool:
    enc = (getattr(sys.stdout, "encoding", None) or "").lower()
    return "utf" in enc


if _supports_unicode():
    _OK   = f"{_Color.OK}✓{_Color.RESET}"
    _WARN = f"{_Color.WARN}!{_Color.RESET}"
    _BAD  = f"{_Color.BAD}✗{_Color.RESET}"
else:
    _OK   = f"{_Color.OK}OK {_Color.RESET}"
    _WARN = f"{_Color.WARN}!  {_Color.RESET}"
    _BAD  = f"{_Color.BAD}X  {_Color.RESET}"


def _check(label: str, status: str, detail: str = "") -> bool:
    """Print one row, return True if status is 'ok'."""
    icon = {"ok": _OK, "warn": _WARN, "bad": _BAD}.get(status, _WARN)
    line = f"  {icon}  {label:<32}"
    if detail:
        line += f"{_Color.DIM} {detail}{_Color.RESET}"
    print(line)
    return status == "ok"


# ── Individual probes ────────────────────────────────────────────────────────

def _check_python() -> bool:
    v = sys.version_info
    if v >= (3, 10):
        return _check("python", "ok", f"{v.major}.{v.minor}.{v.micro}")
    return _check("python", "bad",
                  f"{v.major}.{v.minor} — need ≥ 3.10")


def _check_workspace() -> bool:
    from . import tools as _t
    ws = _t.WORKSPACE_ROOT
    if not ws.exists():
        return _check("workspace", "bad", f"{ws} does not exist")
    writable = os.access(ws, os.W_OK)
    if not writable:
        return _check("workspace", "warn", f"{ws} not writable")
    return _check("workspace", "ok", str(ws))


def _check_disk(min_gb: float = 1.0) -> bool:
    from . import tools as _t
    try:
        total, used, free = shutil.disk_usage(_t.WORKSPACE_ROOT)
    except Exception as e:
        return _check("disk space", "warn", f"could not stat: {e}")
    free_gb = free / 1024 ** 3
    if free_gb < min_gb:
        return _check("disk space", "warn",
                      f"{free_gb:.1f} GB free — recommend ≥ {min_gb} GB")
    return _check("disk space", "ok", f"{free_gb:.1f} GB free")


def _check_ollama(cfg: dict) -> bool:
    url = (os.environ.get("OLLAMA_URL")
           or cfg.get("ollama_url")
           or "http://localhost:11434").rstrip("/")
    try:
        r = requests.get(f"{url}/api/tags", timeout=3)
        r.raise_for_status()
        models = [m.get("name") for m in (r.json().get("models") or [])]
    except Exception as e:
        return _check("ollama reachable", "bad",
                      f"{url} — {type(e).__name__}; run `ollama serve`")
    msg = f"{url} — {len(models)} model(s)"
    _check("ollama reachable", "ok", msg)

    # Specific model presence check
    wanted = (os.environ.get("LLMAI_MODEL")
              or cfg.get("model")
              or "qwen2.5-coder")
    base = wanted.split(":")[0]
    if any(m.startswith(base) for m in models):
        _check(f"model: {wanted}", "ok", "")
    else:
        _check(f"model: {wanted}", "warn",
               f"not pulled — run `ollama pull {wanted}`")

    embed_model = "nomic-embed-text"
    if any(m.startswith(embed_model) for m in models):
        _check(f"embed model: {embed_model}", "ok", "")
    else:
        _check(f"embed model: {embed_model}", "warn",
               f"needed for memory + elastic — `ollama pull {embed_model}`")
    return True


def _check_optional_deps() -> None:
    for name, label, extra in [
        ("opentelemetry", "telemetry deps", "[telemetry]"),
        ("pymongo", "memory deps", "[memory]"),
        ("elasticsearch", "elastic deps", "[elastic]"),
        ("tiktoken", "tiktoken (tokens)", None),
    ]:
        try:
            __import__(name)
            _check(label, "ok", "installed")
        except ImportError:
            hint = f"pip install -e \".{extra}\"" if extra else f"pip install {name}"
            _check(label, "warn", f"not installed — {hint}")


def _check_telemetry(cfg: dict) -> None:
    enabled = (os.environ.get("LLMAI_OTEL_ENABLED", "").lower() in ("1", "true")
               or bool(cfg.get("telemetry", {}).get("enabled")))
    if not enabled:
        _check("telemetry", "ok", "disabled (default)")
        return
    endpoint = (os.environ.get("LLMAI_OTEL_ENDPOINT")
                or cfg.get("telemetry", {}).get("endpoint"))
    if not endpoint:
        _check("telemetry", "bad",
               "enabled but no endpoint — set LLMAI_OTEL_ENDPOINT")
        return
    ok = _probe_tcp(endpoint)
    _check("telemetry endpoint", "ok" if ok else "warn",
           f"{endpoint}" + ("" if ok else " — unreachable"))


def _check_memory(cfg: dict) -> None:
    enabled = (os.environ.get("LLMAI_MEMORY_ENABLED", "").lower() in ("1", "true")
               or bool(cfg.get("memory", {}).get("enabled")))
    if not enabled:
        _check("memory (atlas)", "ok", "disabled (default)")
        return
    uri = (os.environ.get("LLMAI_MEMORY_URI")
           or cfg.get("memory", {}).get("uri"))
    if not uri:
        _check("memory (atlas)", "bad",
               "enabled but no URI — set LLMAI_MEMORY_URI")
        return
    # Don't actually connect (would need pymongo + auth). Just verify shape.
    if "mongodb" not in uri.lower():
        _check("memory (atlas)", "warn",
               "URI doesn't look like a mongodb connection string")
        return
    _check("memory (atlas)", "ok", "configured")


def _check_elastic(cfg: dict) -> None:
    enabled = (os.environ.get("LLMAI_ELASTIC_ENABLED", "").lower() in ("1", "true")
               or bool(cfg.get("elastic", {}).get("enabled")))
    if not enabled:
        _check("elastic", "ok", "disabled (default)")
        return
    url = (os.environ.get("LLMAI_ELASTIC_URL")
           or cfg.get("elastic", {}).get("url"))
    cloud_id = (os.environ.get("LLMAI_ELASTIC_CLOUD_ID")
                or cfg.get("elastic", {}).get("cloud_id"))
    if not (url or cloud_id):
        _check("elastic", "bad",
               "enabled but no URL or cloud_id")
        return
    if url:
        try:
            r = requests.get(f"{url.rstrip('/')}/_cluster/health", timeout=5)
            r.raise_for_status()
            status = r.json().get("status", "?")
            tag = "ok" if status in ("green", "yellow") else "warn"
            _check("elastic cluster", tag, f"{url} status={status}")
        except Exception as e:
            _check("elastic cluster", "warn",
                   f"{url} — {type(e).__name__}")
    else:
        _check("elastic (cloud_id)", "ok", "configured (not probed)")


def _check_gitlab() -> None:
    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        _check("gitlab", "ok", "disabled (set GITLAB_TOKEN to enable)")
        return
    url = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
    try:
        r = requests.get(f"{url}/api/v4/user",
                         headers={"PRIVATE-TOKEN": token}, timeout=5)
        if r.status_code == 200:
            who = r.json().get("username", "?")
            _check("gitlab token", "ok", f"{url} as @{who}")
        else:
            _check("gitlab token", "bad",
                   f"{url} returned {r.status_code}")
    except Exception as e:
        _check("gitlab token", "warn",
               f"{url} unreachable — {type(e).__name__}")


def _check_mcp(cfg: dict) -> None:
    env = os.environ.get("LLMAI_MCP_ENABLED", "").lower()
    enabled = (env in ("1", "true", "yes", "on")
               or (env == "" and bool(cfg.get("mcp", {}).get("enabled"))))
    if not enabled:
        _check("mcp", "ok", "disabled (default)")
        return
    try:
        import mcp  # noqa: F401
    except ImportError:
        _check("mcp sdk", "bad",
               "enabled but not installed — pip install 'llmai-agent[mcp]'")
        return
    _check("mcp sdk", "ok", "installed")
    servers = cfg.get("mcp", {}).get("servers", {})
    if not servers:
        _check("mcp servers", "warn", "enabled but no servers configured")
        return
    for name, raw in servers.items():
        cmd = (raw or {}).get("command", "")
        if not cmd:
            _check(f"mcp:{name}", "bad", "missing 'command'")
            continue
        if shutil.which(cmd):
            detail = f"command '{cmd}' found"
            if cmd in ("npx", "npm", "node"):
                detail += " (Node.js runtime)"
            _check(f"mcp:{name}", "ok", detail)
        else:
            hint = " — install Node.js >= 18" if cmd in ("npx", "npm", "node") else ""
            _check(f"mcp:{name}", "bad", f"command '{cmd}' not on PATH{hint}")


def _probe_tcp(url_or_host: str) -> bool:
    """Best-effort TCP connect to verify a host:port is reachable."""
    try:
        parsed = urlparse(url_or_host if "://" in url_or_host
                          else f"http://{url_or_host}")
        host = parsed.hostname or url_or_host
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=3):
            return True
    except Exception:
        return False


# ── Entry point ──────────────────────────────────────────────────────────────

def _load_config() -> dict:
    for p in [
        Path.cwd() / "llmai.json",
        Path.home() / ".llmai" / "config.json",
        Path(__file__).resolve().parent.parent / "config.json",
    ]:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def run(args: Iterable[str] = ()) -> int:
    """Print the diagnostic report. Returns POSIX exit code."""
    print(f"\nLLMai doctor — {platform.system()} {platform.release()}\n")
    cfg = _load_config()

    print("[Core]")
    py_ok = _check_python()
    _check_workspace()
    _check_disk()
    _check_ollama(cfg)

    print("\n[Optional dependencies]")
    _check_optional_deps()

    print("\n[Layers]")
    _check_telemetry(cfg)
    _check_memory(cfg)
    _check_elastic(cfg)

    print("\n[Integrations]")
    _check_gitlab()
    _check_mcp(cfg)

    print()
    return 0 if py_ok else 1


def main() -> int:
    """Console-script entry point: `llmai-doctor`."""
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
