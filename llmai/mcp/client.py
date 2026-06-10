"""
Per-server MCP connection management (async side).

Each server runs as a local subprocess speaking MCP over stdio. The
stdio_client / ClientSession context managers must be entered and exited
in the same asyncio task (anyio cancel-scope rule), so each connection
owns a dedicated long-lived task that holds the contexts open until
stopped.

All code here runs on the bridge's background event loop — never call
these coroutines from another loop directly.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")

HANDSHAKE_TIMEOUT_S = 10.0


@dataclass
class McpServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    allow: list[str] = field(default_factory=list)


def _expand_env(value: str) -> str:
    """Expand ``${VAR}`` references from the parent process environment."""
    def repl(m: re.Match) -> str:
        var = m.group(1)
        val = os.environ.get(var)
        if val is None:
            logger.warning("MCP config references unset env var ${%s}", var)
            return ""
        return val
    return _ENV_VAR_RE.sub(repl, value)


def build_subprocess_env(extra: dict[str, str]) -> dict[str, str]:
    """Env for an MCP server subprocess: minimal safe defaults + named vars.

    Deliberately NOT the agent's full environment — unrelated secrets
    (API keys, tokens) must not leak into MCP server processes. The SDK's
    default environment carries just PATH/HOME-class variables.
    """
    from mcp.client.stdio import get_default_environment
    return {**get_default_environment(), **extra}


def parse_servers_config(block: dict) -> list[McpServerConfig]:
    """Parse the ``mcp.servers`` config block into typed configs.

    Malformed entries are skipped with a warning — one bad server must
    not take down the others.
    """
    configs: list[McpServerConfig] = []
    for name, raw in (block or {}).items():
        if not isinstance(raw, dict) or not raw.get("command"):
            logger.warning("MCP server '%s' skipped: missing 'command'", name)
            continue
        configs.append(McpServerConfig(
            name=str(name),
            command=str(raw["command"]),
            args=[str(a) for a in raw.get("args", [])],
            env={str(k): _expand_env(str(v)) for k, v in (raw.get("env") or {}).items()},
            allow=[str(t) for t in raw.get("allow", [])],
        ))
    return configs


class McpServerConnection:
    """One live MCP server: subprocess + session held open by a task."""

    def __init__(self, config: McpServerConfig):
        self.config = config
        self._session: Optional[Any] = None
        self._task: Optional[asyncio.Task] = None
        self._stop_evt: Optional[asyncio.Event] = None

    @property
    def connected(self) -> bool:
        return self._session is not None

    async def start(self) -> list[tuple[str, str, dict]]:
        """Spawn the server, handshake, and return its tool list.

        Raises on failure (caller converts to a failed server state).
        """
        # Lazy SDK import — only fails if [mcp] extra missing AND enabled.
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=self.config.command,
            args=self.config.args,
            env=build_subprocess_env(self.config.env),
        )
        loop = asyncio.get_running_loop()
        ready: asyncio.Future = loop.create_future()
        self._stop_evt = asyncio.Event()

        async def _run() -> None:
            try:
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        listed = await session.list_tools()
                        self._session = session
                        if not ready.done():
                            ready.set_result([
                                (t.name, t.description or "", t.inputSchema or {})
                                for t in listed.tools
                            ])
                        await self._stop_evt.wait()
            except Exception as e:  # noqa: BLE001 — must never leak
                if not ready.done():
                    ready.set_exception(e)
                else:
                    logger.warning("MCP server '%s' died: %s", self.config.name, e)
            finally:
                self._session = None

        self._task = asyncio.ensure_future(_run())
        return await asyncio.wait_for(ready, timeout=HANDSHAKE_TIMEOUT_S)

    async def call(self, tool: str, args: dict, timeout_s: float) -> Any:
        """Invoke *tool*; returns the raw MCP result. Raises on failure."""
        if self._session is None:
            raise ConnectionError(f"MCP server '{self.config.name}' is not connected")
        return await asyncio.wait_for(
            self._session.call_tool(tool, args or {}), timeout=timeout_s
        )

    async def stop(self) -> None:
        if self._stop_evt is not None:
            self._stop_evt.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self._session = None
