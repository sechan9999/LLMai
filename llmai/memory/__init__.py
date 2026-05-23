"""
Persistent agent memory backed by MongoDB Atlas.

Layered design:
  - sessions:   raw transcripts, keyed by session_id
  - summaries:  compressed context (vector-embedded) for cross-session recall
  - knowledge:  per-workspace facts/decisions extracted at session end

Opt-in. Off by default — set LLMAI_MEMORY_ENABLED=true or configure the
``memory`` block in config.json. Every operation is wrapped in try/except;
Atlas outages never break the agent loop.

Public API:
  - MemoryStore: the singleton handle (initialized once at startup)
  - is_enabled(): True if memory is configured and reachable
  - get_store(): the active store (returns None when disabled)
"""
from __future__ import annotations

from typing import Optional

from .store import MemoryStore

_STORE: Optional[MemoryStore] = None


def init(config: Optional[dict] = None) -> Optional[MemoryStore]:
    """Initialize the memory store. Idempotent.

    Returns the active store (or None if disabled / init failed).
    """
    global _STORE
    if _STORE is not None:
        return _STORE
    store = MemoryStore.from_config(config or {})
    if store is not None and store.connect():
        _STORE = store
    return _STORE


def is_enabled() -> bool:
    return _STORE is not None and _STORE.connected


def get_store() -> Optional[MemoryStore]:
    return _STORE


__all__ = ["MemoryStore", "init", "is_enabled", "get_store"]
