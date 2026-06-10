"""
MCP client layer: connect the agent to external MCP servers.

Tools served by any spec-compliant MCP server (stdio transport) are
discovered at startup and registered into the agent's tool registry as
``mcp__{server}__{tool}``, gated by the permission system.

Opt-in. Off by default — set ``LLMAI_MCP_ENABLED=true`` or configure the
``mcp`` block in config.json. Every operation wraps failures so the
agent loop never crashes because an MCP server is unreachable.

Public API:
  - init(config): start bridge + connect servers; returns is_enabled()
  - is_enabled(): True when at least one server is connected
  - get_registrations(): (spec, handler) pairs for tools.py
  - get_server_states(): per-server status for doctor / CLI
  - shutdown(): terminate subprocesses (also registered via atexit)
  - MCP_DEFAULT_PERMISSIONS: populated during init(); merged into the
    permission rules by the entry points (never at import time)
"""
from __future__ import annotations

import atexit
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Populated during init(): {qualified_name: "allow" | "ask"}.
# Import-safe — empty dict until MCP is actually enabled and connected.
MCP_DEFAULT_PERMISSIONS: dict[str, str] = {}

_BRIDGE = None      # McpBridge
_REGISTRY = None    # McpRegistry
_STATES: list = []  # list[McpServerState]


def _env_flag(name: str) -> Optional[bool]:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip().lower() in ("1", "true", "yes", "on")


def init(config: Optional[dict] = None) -> bool:
    """Initialize the MCP layer. Idempotent. Never raises.

    *config* is the ``mcp`` block from config.json. The env var
    ``LLMAI_MCP_ENABLED`` always wins over the config flag.
    """
    global _BRIDGE, _REGISTRY
    if _BRIDGE is not None:
        return is_enabled()

    config = config or {}
    enabled = _env_flag("LLMAI_MCP_ENABLED")
    if enabled is None:
        enabled = bool(config.get("enabled", False))
    if not enabled:
        return False

    try:
        import mcp as _sdk  # noqa: F401 — availability probe only
    except ImportError:
        logger.warning(
            "MCP enabled but the 'mcp' package is not installed. "
            "Run: pip install 'llmai-agent[mcp]'"
        )
        return False

    from .bridge import McpBridge, McpServerState
    from .client import parse_servers_config
    from .registry import McpRegistry

    servers = parse_servers_config(config.get("servers", {}))
    if not servers:
        logger.warning("MCP enabled but no servers configured under mcp.servers")
        return False

    bridge = McpBridge(call_timeout_s=float(config.get("call_timeout_s", 30)))
    bridge.start()
    registry = McpRegistry(call_fn=bridge.call)

    for server_cfg in servers:
        ok, payload = bridge.connect(server_cfg)
        if not ok:
            logger.warning("MCP server '%s' failed: %s", server_cfg.name, payload)
            _STATES.append(McpServerState(
                name=server_cfg.name, status="failed", error=str(payload)))
            continue
        specs = registry.add_server_tools(server_cfg.name, payload)
        for spec in specs:
            MCP_DEFAULT_PERMISSIONS[spec.qualified] = (
                "allow" if spec.name in server_cfg.allow else "ask"
            )
        _STATES.append(McpServerState(
            name=server_cfg.name, status="connected", tools=specs))

    _BRIDGE = bridge
    _REGISTRY = registry
    atexit.register(shutdown)
    return is_enabled()


def is_enabled() -> bool:
    return _BRIDGE is not None and any(s.status == "connected" for s in _STATES)


def get_registrations() -> list:
    """(McpToolSpec, handler) pairs — empty when disabled."""
    if _REGISTRY is None:
        return []
    return _REGISTRY.get_registrations()


def get_server_states() -> list:
    return list(_STATES)


def shutdown() -> None:
    """Stop the bridge and all server subprocesses. Idempotent."""
    global _BRIDGE, _REGISTRY
    bridge = _BRIDGE
    _BRIDGE = None
    _REGISTRY = None
    _STATES.clear()
    MCP_DEFAULT_PERMISSIONS.clear()
    if bridge is not None:
        try:
            bridge.stop()
        except Exception as e:  # noqa: BLE001
            logger.debug("MCP shutdown error: %s", e)


__all__ = [
    "MCP_DEFAULT_PERMISSIONS",
    "init",
    "is_enabled",
    "get_registrations",
    "get_server_states",
    "shutdown",
]
