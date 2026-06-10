"""
Sync facade over the async MCP client.

The MCP SDK is asyncio-only; the CLI agent loop is synchronous and the
WebSocket loop executes tools in a thread executor. McpBridge runs a
dedicated daemon thread with its own event loop, and every public method
is a plain blocking call — callers never touch asyncio.

One reconnect attempt is made when a call fails on a dead server; after
that, calls return error strings until the process restarts.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from dataclasses import dataclass, field
from typing import Literal, Optional

from .client import McpServerConfig, McpServerConnection
from .registry import flatten_result

logger = logging.getLogger(__name__)

DEFAULT_CALL_TIMEOUT_S = 30.0


@dataclass
class McpServerState:
    name: str
    status: Literal["connected", "failed", "disabled"]
    tools: list = field(default_factory=list)   # list[McpToolSpec], filled by __init__.py
    error: Optional[str] = None


class McpBridge:
    """Background event loop + blocking facade for MCP sessions."""

    def __init__(self, call_timeout_s: float = DEFAULT_CALL_TIMEOUT_S):
        self.call_timeout_s = call_timeout_s
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connections: dict[str, McpServerConnection] = {}
        self._lock = threading.Lock()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the event-loop thread. Idempotent."""
        with self._lock:
            if self._loop is not None:
                return
            loop = asyncio.new_event_loop()
            ready = threading.Event()

            def _run() -> None:
                asyncio.set_event_loop(loop)
                ready.set()
                loop.run_forever()

            self._thread = threading.Thread(target=_run, name="llmai-mcp", daemon=True)
            self._thread.start()
            ready.wait(timeout=5.0)
            self._loop = loop

    def stop(self) -> None:
        """Disconnect all servers and stop the loop thread. Idempotent."""
        with self._lock:
            loop = self._loop
            if loop is None:
                return
            self._loop = None
        for conn in list(self._connections.values()):
            try:
                asyncio.run_coroutine_threadsafe(conn.stop(), loop).result(timeout=6.0)
            except Exception as e:  # noqa: BLE001
                logger.debug("MCP server '%s' stop error: %s", conn.config.name, e)
        self._connections.clear()
        loop.call_soon_threadsafe(loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    # ── Connections ──────────────────────────────────────────────────────────

    def connect(self, config: McpServerConfig) -> tuple[bool, object]:
        """Connect one server (blocking).

        Returns (True, tool_list) or (False, error_message).
        """
        if self._loop is None:
            return False, "bridge not started"
        conn = McpServerConnection(config)
        try:
            fut = asyncio.run_coroutine_threadsafe(conn.start(), self._loop)
            tools = fut.result(timeout=15.0)
        except concurrent.futures.TimeoutError:
            return False, "handshake timed out"
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"
        self._connections[config.name] = conn
        logger.info("MCP server '%s' connected (%d tools)", config.name, len(tools))
        return True, tools

    def call(self, server: str, tool: str, args: dict) -> str:
        """Blocking tool invocation; always returns a string, never raises."""
        result = self._call_once(server, tool, args)
        if result is not None:
            return result
        # Dead session — one reconnect attempt, then one retry.
        conn = self._connections.get(server)
        if conn is not None:
            logger.warning("MCP server '%s' unreachable — reconnecting once", server)
            ok, _ = self.connect(conn.config)
            if ok:
                result = self._call_once(server, tool, args)
                if result is not None:
                    return result
        return f"Error: MCP server '{server}' is not connected"

    def _call_once(self, server: str, tool: str, args: dict) -> Optional[str]:
        """One call attempt. None signals 'session dead, retry may help'."""
        if self._loop is None:
            return "Error: MCP bridge is not running"
        conn = self._connections.get(server)
        if conn is None:
            return f"Error: Unknown MCP server '{server}'"
        if not conn.connected:
            return None
        try:
            fut = asyncio.run_coroutine_threadsafe(
                conn.call(tool, args, timeout_s=self.call_timeout_s), self._loop
            )
            raw = fut.result(timeout=self.call_timeout_s + 5.0)
        except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
            return f"Error: mcp__{server}__{tool} timed out after {self.call_timeout_s:.0f}s"
        except (ConnectionError, BrokenPipeError, EOFError):
            return None  # session dead — caller may reconnect + retry
        except Exception as e:  # noqa: BLE001 — tool-level failure, no retry
            logger.warning("MCP call %s/%s failed: %s", server, tool, e)
            return f"Error: mcp__{server}__{tool} failed: {type(e).__name__}: {e}"
        return flatten_result(raw)
