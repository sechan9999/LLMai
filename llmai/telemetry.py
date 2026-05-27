"""
OpenTelemetry instrumentation for llmai agent loops.

Opt-in. Off by default (privacy-first). When disabled or unavailable, every
helper here becomes a no-op via OTel's default NoOp providers — the agent
runs identically with zero overhead and zero new dependencies at runtime.

Env vars (override config.json["telemetry"]):
  LLMAI_OTEL_ENABLED      "true"/"false"  (default: false)
  LLMAI_OTEL_ENDPOINT     OTLP HTTP base, e.g. http://localhost:4318
  LLMAI_OTEL_SERVICE_NAME default: llmai-agent
  LLMAI_OTEL_HEADERS      URL-encoded k=v&k=v, e.g.
                             Authorization=Api-Token%20dt0c01.xxx
  LLMAI_OTEL_CONSOLE      "true" to also dump spans to stdout (dev)
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional
from urllib.parse import unquote

logger = logging.getLogger(__name__)

_INITIALIZED = False
_ACTIVE = False
_TRACER: Any = None
_METER: Any = None
_METRICS: dict[str, Any] = {}


# ── Public init ──────────────────────────────────────────────────────────────

def init(config: Optional[dict] = None) -> bool:
    """Initialize OTel from env vars and optional config block.

    Idempotent: subsequent calls return the cached result. Failures are
    logged and swallowed — telemetry is never in the critical path.

    Returns:
        True if telemetry is active, False if disabled or init failed.
    """
    global _INITIALIZED, _ACTIVE, _TRACER, _METER
    if _INITIALIZED:
        return _ACTIVE
    _INITIALIZED = True

    cfg = (config or {}) if isinstance(config, dict) else {}
    enabled = _truthy(os.environ.get("LLMAI_OTEL_ENABLED")) or bool(cfg.get("enabled"))
    if not enabled:
        return False

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import (
            ConsoleMetricExporter,
            PeriodicExportingMetricReader,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
    except ImportError as e:
        logger.warning(
            "OpenTelemetry packages not installed (%s); telemetry disabled. "
            "Run: pip install -e '.[telemetry]'",
            e,
        )
        return False

    endpoint = (
        os.environ.get("LLMAI_OTEL_ENDPOINT")
        or cfg.get("endpoint")
        or ""
    ).rstrip("/")
    service = (
        os.environ.get("LLMAI_OTEL_SERVICE_NAME")
        or cfg.get("service_name")
        or "llmai-agent"
    )
    headers = _parse_headers(os.environ.get("LLMAI_OTEL_HEADERS")) or dict(
        cfg.get("headers") or {}
    )
    console = _truthy(os.environ.get("LLMAI_OTEL_CONSOLE")) or bool(
        cfg.get("console")
    )

    if not endpoint and not console:
        logger.warning(
            "Telemetry enabled but no endpoint or console exporter configured; "
            "set LLMAI_OTEL_ENDPOINT or LLMAI_OTEL_CONSOLE=true."
        )
        return False

    resource = Resource.create({
        "service.name": service,
        "service.namespace": "llmai",
        "service.version": _detect_version(),
    })

    # ── Traces ──
    tp = TracerProvider(resource=resource)
    if endpoint:
        tp.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=f"{endpoint}/v1/traces",
                    headers=headers or None,
                )
            )
        )
    if console:
        tp.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(tp)

    # ── Metrics ──
    readers = []
    if endpoint:
        readers.append(
            PeriodicExportingMetricReader(
                OTLPMetricExporter(
                    endpoint=f"{endpoint}/v1/metrics",
                    headers=headers or None,
                ),
                export_interval_millis=15_000,
            )
        )
    if console:
        readers.append(
            PeriodicExportingMetricReader(
                ConsoleMetricExporter(),
                export_interval_millis=60_000,
            )
        )
    if readers:
        mp = MeterProvider(resource=resource, metric_readers=readers)
        metrics.set_meter_provider(mp)

    _TRACER = trace.get_tracer("llmai.agent")
    _METER = metrics.get_meter("llmai.agent")
    _build_metrics()
    _ACTIVE = True
    logger.info(
        "Telemetry active: endpoint=%s service=%s console=%s",
        endpoint or "(none)", service, console,
    )
    return True


def is_active() -> bool:
    """Return True if telemetry is initialized and exporting."""
    return _ACTIVE


class _NoopSpan:
    """Stand-in span used when OTel isn't installed at all.

    Implements the methods our instrumentation actually calls
    (``set_attribute``, context-manager protocol). Real OTel NoOp spans
    have a richer API but we only need this surface.
    """
    def set_attribute(self, *args, **kwargs): return None
    def __enter__(self): return self
    def __exit__(self, *exc_info): return False


class _NoopTracer:
    """Drop-in tracer that emits no-op spans without importing opentelemetry."""
    def start_as_current_span(self, _name, *args, **kwargs):
        return _NoopSpan()


_NOOP_TRACER = _NoopTracer()


def tracer():
    """Return the active tracer, or a true no-op if OTel is unavailable.

    We DON'T try to import ``opentelemetry`` here on the fallback path —
    the telemetry layer is opt-in, and the package is an extra. Importing
    it from the fallback would crash users who never enabled telemetry.
    """
    if _TRACER is not None:
        return _TRACER
    try:
        from opentelemetry import trace
        return trace.get_tracer("llmai.agent")
    except ImportError:
        return _NOOP_TRACER


# ── Span context managers ────────────────────────────────────────────────────

@contextmanager
def turn_span(
    *, mode: str, provider: str, model: str, input_chars: int
) -> Iterator[Any]:
    """Wrap one user turn (root span for the whole multi-step interaction)."""
    with tracer().start_as_current_span("agent.turn") as span:
        _set(span, "agent.mode", mode)
        _set(span, "agent.provider", provider)
        _set(span, "agent.model", model)
        _set(span, "agent.input.chars", input_chars)
        _inc("turns", {"mode": mode, "provider": provider})
        try:
            yield span
        except BaseException as exc:
            _set(span, "agent.outcome", "error")
            _set(span, "error.type", type(exc).__name__)
            raise
        else:
            _set(span, "agent.outcome", "ok")


@contextmanager
def iteration_span(*, number: int, tokens_estimate: int) -> Iterator[Any]:
    """Wrap one iteration of the observe→judge→act loop."""
    with tracer().start_as_current_span("agent.iteration") as span:
        _set(span, "iteration.number", number)
        _set(span, "tokens.estimate.before", tokens_estimate)
        yield span


@contextmanager
def llm_span(
    *, model: str, provider: str, message_count: int, streamed: bool
) -> Iterator[Any]:
    """Wrap a single LLM chat completion request."""
    start = time.monotonic()
    with tracer().start_as_current_span("llm.chat") as span:
        _set(span, "llm.model", model)
        _set(span, "llm.provider", provider)
        _set(span, "llm.messages.count", message_count)
        _set(span, "llm.streamed", streamed)
        try:
            yield span
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000
            _set(span, "llm.latency_ms", round(elapsed_ms, 2))
            _record(
                "llm_latency", elapsed_ms,
                {"model": model, "provider": provider},
            )


@contextmanager
def tool_span(*, name: str, args: dict) -> Iterator[tuple[Any, "ToolOutcome"]]:
    """Wrap a single tool invocation. Caller must populate the outcome dict.

    Yields ``(span, outcome)``. The caller updates ``outcome`` with:
      outcome.permission  "allow" | "ask_allow" | "ask_deny" | "deny"
      outcome.perm_latency_ms  seconds the user took to decide (0 if no prompt)
      outcome.error       True if execution failed or permission denied
      outcome.result_chars  size of the result string
    """
    start = time.monotonic()
    outcome = ToolOutcome()
    with tracer().start_as_current_span("tool.invocation") as span:
        _set(span, "tool.name", name)
        _set(span, "tool.args.preview", _preview_args(args))
        try:
            yield span, outcome
        finally:
            total_ms = (time.monotonic() - start) * 1000
            exec_ms = max(0.0, total_ms - outcome.perm_latency_ms)
            _set(span, "tool.permission.outcome", outcome.permission)
            _set(span, "tool.permission.latency_ms", round(outcome.perm_latency_ms, 2))
            _set(span, "tool.exec.latency_ms", round(exec_ms, 2))
            _set(span, "tool.result.chars", outcome.result_chars)
            _set(span, "error", outcome.error)
            _inc(
                "tool_count",
                {
                    "tool.name": name,
                    "permission.outcome": outcome.permission,
                    "error": str(outcome.error).lower(),
                },
            )
            _record("tool_latency", exec_ms, {"tool.name": name})


def record_tokens(*, direction: str, count: int, model: str) -> None:
    """Record an LLM token count (direction is 'in' or 'out')."""
    if count > 0:
        _record(
            "llm_tokens", count,
            {"direction": direction, "model": model},
        )


class ToolOutcome:
    """Mutable bag of attributes the caller fills in during a tool_span."""
    __slots__ = ("permission", "perm_latency_ms", "error", "result_chars")

    def __init__(self) -> None:
        self.permission: str = "unknown"
        self.perm_latency_ms: float = 0.0
        self.error: bool = False
        self.result_chars: int = 0


# ── Helpers ──────────────────────────────────────────────────────────────────

def _truthy(s: Optional[str]) -> bool:
    return (s or "").strip().lower() in ("1", "true", "yes", "on")


def _parse_headers(raw: Optional[str]) -> dict[str, str]:
    if not raw:
        return {}
    out: dict[str, str] = {}
    for pair in raw.split("&"):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        out[unquote(k).strip()] = unquote(v).strip()
    return out


def _detect_version() -> str:
    try:
        from importlib.metadata import version
        return version("llmai-agent")
    except Exception:
        return "unknown"


def _build_metrics() -> None:
    if _METER is None:
        return
    _METRICS.update({
        "turns": _METER.create_counter(
            "llmai.agent.turns",
            description="Agent turns started",
        ),
        "llm_latency": _METER.create_histogram(
            "llmai.llm.latency",
            unit="ms",
            description="LLM chat completion latency",
        ),
        "llm_tokens": _METER.create_histogram(
            "llmai.llm.tokens",
            unit="token",
            description="Estimated tokens per LLM call",
        ),
        "tool_count": _METER.create_counter(
            "llmai.tool.invocations",
            description="Tool invocations attempted",
        ),
        "tool_latency": _METER.create_histogram(
            "llmai.tool.latency",
            unit="ms",
            description="Tool execution latency (excludes permission wait)",
        ),
    })


def _set(span: Any, key: str, value: Any) -> None:
    """Safe attribute setter (NoOp spans accept this but we still guard)."""
    try:
        span.set_attribute(key, value)
    except Exception:
        pass


def _inc(metric: str, attrs: dict) -> None:
    inst = _METRICS.get(metric)
    if inst is not None:
        try:
            inst.add(1, attributes=attrs)
        except Exception:
            pass


def _record(metric: str, value: float, attrs: dict) -> None:
    inst = _METRICS.get(metric)
    if inst is not None:
        try:
            inst.record(value, attributes=attrs)
        except Exception:
            pass


def _preview_args(args: dict) -> str:
    """Render args as a short, PII-free preview (≤200 chars)."""
    parts: list[str] = []
    for k, v in args.items():
        s = repr(v) if not isinstance(v, str) else v
        if len(s) > 50:
            s = s[:50] + "…"
        parts.append(f"{k}={s}")
    out = ", ".join(parts)
    return out[:200]


_TIKTOKEN_ENC: Any = None
_TIKTOKEN_TRIED = False


def _get_tiktoken_encoding() -> Any:
    """Return a cached tiktoken encoding, or None if unavailable.

    Uses ``cl100k_base`` — a reasonable approximation across OpenAI,
    Anthropic, and most local-model tokenizers. Off by a few percent vs.
    the model's true tokenizer, but far more accurate than ``char/4``.
    """
    global _TIKTOKEN_ENC, _TIKTOKEN_TRIED
    if _TIKTOKEN_TRIED:
        return _TIKTOKEN_ENC
    _TIKTOKEN_TRIED = True
    try:
        import tiktoken
        _TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _TIKTOKEN_ENC = None
    return _TIKTOKEN_ENC


def _count_tokens(enc: Any, text: str) -> int:
    if not text:
        return 0
    if enc is not None:
        try:
            return len(enc.encode(text, disallowed_special=()))
        except Exception:
            pass
    return len(text) // 4


def estimate_tokens(messages: list[dict]) -> int:
    """Estimate total tokens for a messages list.

    Uses ``tiktoken`` (cl100k_base) when installed; otherwise falls back
    to a ``char/4`` heuristic. Install with ``pip install tiktoken`` for
    ~30% better accuracy on code-heavy contexts (where char/4 systematically
    over-counts).
    """
    import json
    enc = _get_tiktoken_encoding()
    total = 0
    for m in messages:
        content = m.get("content") or ""
        if not isinstance(content, str):
            content = json.dumps(content)
        total += _count_tokens(enc, content)
        for tc in (m.get("tool_calls") or []):
            fn = tc.get("function", {})
            total += _count_tokens(enc, fn.get("name", ""))
            args = fn.get("arguments", "")
            if not isinstance(args, str):
                args = json.dumps(args)
            total += _count_tokens(enc, args)
    return total
