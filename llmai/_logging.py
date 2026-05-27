"""
Logging configuration helpers.

By default LLMai uses the Python default logging format (human-readable).
Set ``LLMAI_LOG_FORMAT=json`` to emit one JSON object per log record on
stderr — useful when shipping to log aggregators (Loki, ELK, Datadog, etc).

Call :func:`configure_logging` once at startup. Idempotent.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as a single JSON line.

    Stays compact and stable: standard fields first, then any ``extra=``
    keys merged in. ``exc_info`` becomes a multi-line ``error`` field.
    """

    _STANDARD = {
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process",
        "taskName", "message", "asctime",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        # Merge `extra={...}` fields that aren't in the standard set
        for k, v in record.__dict__.items():
            if k in self._STANDARD or k.startswith("_"):
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except (TypeError, ValueError):
                payload[k] = repr(v)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str | None = None) -> None:
    """Set up the root logger once based on env vars.

    Env vars:
      LLMAI_LOG_FORMAT  "text" (default) | "json"
      LLMAI_LOG_LEVEL   DEBUG | INFO | WARNING (default) | ERROR
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    fmt = (os.environ.get("LLMAI_LOG_FORMAT") or "text").strip().lower()
    lvl = (level or os.environ.get("LLMAI_LOG_LEVEL") or "WARNING").upper()

    handler = logging.StreamHandler(sys.stderr)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))

    root = logging.getLogger()
    # Remove any prior handlers (e.g. uvicorn's) so our format wins
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    try:
        root.setLevel(getattr(logging, lvl))
    except AttributeError:
        root.setLevel(logging.WARNING)
