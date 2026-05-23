"""
AgentLoop: observe → judge → act × while(True)

This is the core difference from a chatbot.
A chatbot: one input → one output.
An agent:  one input → loop until goal reached.
"""
import json
import logging
import time
from typing import Callable

from . import memory, telemetry
from .llm import OllamaClient
from .tools import TOOL_DEFINITIONS, execute_tool, WORKSPACE_ROOT
from .permissions import PermissionManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert coding assistant running locally. Help the user with software development tasks.

You have tools for reading/writing files, running shell commands, and searching code. Work methodically:
- Read files before modifying them
- Verify your changes are correct
- Run tests when appropriate
- Be concise; stop and summarize when the task is done

Always read a file before editing it to get the exact content."""


PrintFn = Callable[..., None]


class AgentLoop:
    """Synchronous agent loop used by the CLI REPL.

    The loop calls the LLM, processes any tool calls, feeds results back,
    and repeats until the LLM responds with text only (no more tool calls)
    or the iteration limit is reached.

    Attributes:
        llm: The Ollama client instance.
        permissions: Permission manager for gating tool execution.
        max_iterations: Safety cap on agentic loop iterations.
        messages: Full conversation history.
    """

    def __init__(
        self,
        llm: OllamaClient,
        permissions: PermissionManager,
        max_iterations: int = 20,
    ):
        self.llm = llm
        self.permissions = permissions
        self.max_iterations = max_iterations
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.session_id: str = _new_session_id()
        self.turn_count: int = 0
        self._memory_primed: bool = False

    # ── Public ──────────────────────────────────────────────────────────────

    def run(self, user_input: str, print_fn: PrintFn = print) -> str:
        """Execute one full agent turn (potentially multi-step).

        Args:
            user_input: The user's message.
            print_fn: Callable used for output (default: print).

        Returns:
            The last text response from the LLM.
        """
        self._prime_memory(user_input)
        self.messages.append({"role": "user", "content": user_input})
        last_text = ""
        model_name = getattr(self.llm, "model", "unknown")
        provider = getattr(self.llm, "provider", "ollama")
        self.turn_count += 1

        with telemetry.turn_span(
            mode="cli",
            provider=provider,
            model=model_name,
            input_chars=len(user_input),
        ) as turn:
            iterations_done = 0
            for iteration in range(self.max_iterations):
                iterations_done = iteration + 1
                with telemetry.iteration_span(
                    number=iteration + 1,
                    tokens_estimate=self.token_estimate,
                ):
                    # ── 1. Call LLM ─────────────────────────────────────────
                    try:
                        with telemetry.llm_span(
                            model=model_name,
                            provider=provider,
                            message_count=len(self.messages),
                            streamed=False,
                        ) as llm_s:
                            tokens_in_before = telemetry.estimate_tokens(self.messages)
                            msg = self.llm.chat(self.messages, tools=TOOL_DEFINITIONS)
                            telemetry.record_tokens(
                                direction="in", count=tokens_in_before, model=model_name,
                            )
                            out_chars = len((msg.get("content") or ""))
                            telemetry.record_tokens(
                                direction="out", count=out_chars // 4, model=model_name,
                            )
                            llm_s.set_attribute(
                                "llm.tool_calls.requested",
                                len(msg.get("tool_calls") or []),
                            )
                    except Exception as e:
                        logger.exception("LLM call failed")
                        print_fn(f"\n[LLM error] {e}")
                        break

                    content = msg.get("content") or ""
                    tool_calls = msg.get("tool_calls") or []

                    # ── 2. Print text response ──────────────────────────────
                    if content:
                        print_fn(f"\n{content}")
                        last_text = content

                    # ── 3. Add assistant message to history ─────────────────
                    assistant_msg: dict = {"role": "assistant"}
                    if content:
                        assistant_msg["content"] = content
                    if tool_calls:
                        assistant_msg["tool_calls"] = tool_calls
                    self.messages.append(assistant_msg)

                    # ── 4. No tool calls → done ─────────────────────────────
                    if not tool_calls:
                        break

                    # ── 5. Execute each tool call (observe → act) ───────────
                    for tc in tool_calls:
                        fn_name, fn_args, tc_id = _parse_tool_call(tc)
                        print_fn(f"\n  ⚙  {fn_name}({_fmt_args(fn_args)})")

                        with telemetry.tool_span(name=fn_name, args=fn_args) as (_, oc):
                            perm_start = time.monotonic()
                            allowed = self.permissions.check(fn_name, fn_args)
                            oc.perm_latency_ms = (time.monotonic() - perm_start) * 1000
                            if allowed:
                                oc.permission = "allow"
                                try:
                                    result = execute_tool(fn_name, fn_args)
                                    if result.startswith("Error"):
                                        oc.error = True
                                except Exception as e:
                                    oc.error = True
                                    result = f"Error in {fn_name}: {e}"
                                _print_result(result, print_fn)
                            else:
                                oc.permission = "deny"
                                oc.error = True
                                result = f"Permission denied for {fn_name}"
                                print_fn(f"  ✗  {result}")
                            oc.result_chars = len(result)

                        # Feed result back into context (observe)
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": result,
                        })

            turn.set_attribute("agent.iterations.actual", iterations_done)

        self._persist_turn(model_name, provider)
        return last_text

    def reset(self) -> None:
        """Clear conversation history, keeping only the system prompt.

        On reset we mark the in-flight session as ended and try to extract
        a few reusable facts before wiping in-memory state. Best-effort.
        """
        self._finalize_session()
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.session_id = _new_session_id()
        self.turn_count = 0
        self._memory_primed = False

    @property
    def token_estimate(self) -> int:
        """Rough token count estimate (4 chars ≈ 1 token).

        Counts both content text and any serialized tool_calls so the
        estimate doesn't silently miss large arguments blobs.
        """
        total = 0
        for m in self.messages:
            content = m.get("content") or ""
            total += len(content)
            for tc in (m.get("tool_calls") or []):
                fn = tc.get("function", {})
                total += len(fn.get("name", ""))
                args = fn.get("arguments", "")
                total += len(args) if isinstance(args, str) else len(json.dumps(args))
        return total // 4

    def maybe_compress(self, threshold: int = 50_000) -> None:
        """Summarise old messages when context gets large.

        Keeps the system prompt and last 6 turns, replacing older
        messages with an LLM-generated summary.
        """
        if self.token_estimate < threshold:
            return
        keep_recent = 6
        if len(self.messages) <= 1 + keep_recent:
            return  # nothing meaningful to compress

        system = self.messages[:1]
        old = self.messages[1:-keep_recent]
        recent = self.messages[-keep_recent:]

        # Serialize history into plain text so the summarizer can't be
        # confused by raw tool_calls or system roles.
        transcript = _format_for_summary(old)
        summary_messages = [
            {
                "role": "system",
                "content": (
                    "You summarise programming-assistant conversations. "
                    "Preserve file paths, decisions, and pending work. "
                    "Reply with plain prose only, no tool calls. Max 200 words."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Summarise the conversation below for use as compressed "
                    "context.\n\n--- Conversation ---\n" + transcript
                ),
            },
        ]
        try:
            summary_msg = self.llm.chat(summary_messages)
            summary = summary_msg.get("content") or "(summary unavailable)"
        except Exception:
            logger.exception("Compression LLM call failed")
            summary = "(context compressed; summary unavailable)"

        self.messages = system + [
            {"role": "system", "content": f"[Earlier context summary]\n{summary}"}
        ] + recent


    # ── Memory hooks (best-effort; never raise into the loop) ────────────────

    def _prime_memory(self, first_user_input: str) -> None:
        """Inject recent prior-session summaries as a system message (once)."""
        if self._memory_primed:
            return
        self._memory_primed = True
        store = memory.get_store()
        if store is None:
            return
        try:
            summaries = store.recent_summaries(str(WORKSPACE_ROOT))
        except Exception:
            logger.debug("recent_summaries lookup failed", exc_info=True)
            return
        if not summaries:
            return
        lines = ["[Memory from prior sessions in this workspace]"]
        for s in summaries:
            when = s.get("created_at")
            when_str = when.strftime("%Y-%m-%d") if when else "?"
            text = (s.get("summary") or "").strip()
            if text:
                lines.append(f"• ({when_str}) {text}")
        if len(lines) > 1:
            # Insert AFTER the system prompt so the model treats it as context.
            self.messages.insert(1, {"role": "system", "content": "\n".join(lines)})

    def _persist_turn(self, model_name: str, provider: str) -> None:
        store = memory.get_store()
        if store is None:
            return
        try:
            store.save_session(
                session_id=self.session_id,
                workspace_path=str(WORKSPACE_ROOT),
                provider=provider,
                model=model_name,
                messages=self.messages,
                token_estimate=self.token_estimate,
                turn_count=self.turn_count,
            )
        except Exception:
            logger.debug("save_session failed", exc_info=True)

    def _finalize_session(self) -> None:
        """Mark session ended, extract facts, save summary."""
        store = memory.get_store()
        if store is None or self.turn_count == 0:
            return
        try:
            store.save_session(
                session_id=self.session_id,
                workspace_path=str(WORKSPACE_ROOT),
                provider=getattr(self.llm, "provider", "ollama"),
                model=getattr(self.llm, "model", "unknown"),
                messages=self.messages,
                token_estimate=self.token_estimate,
                turn_count=self.turn_count,
                ended=True,
            )
        except Exception:
            logger.debug("session finalize save failed", exc_info=True)

        # Best-effort summary + knowledge extraction (one extra LLM call each).
        try:
            summary = _summarize_for_memory(self.llm, self.messages)
            if summary:
                store.save_summary(
                    session_id=self.session_id,
                    workspace_path=str(WORKSPACE_ROOT),
                    summary=summary,
                    source_token_count=self.token_estimate,
                )
        except Exception:
            logger.debug("summary extraction failed", exc_info=True)

        try:
            facts = _extract_facts_for_memory(self.llm, self.messages)
            if facts:
                store.save_knowledge(
                    workspace_path=str(WORKSPACE_ROOT),
                    source_session_id=self.session_id,
                    items=facts,
                )
        except Exception:
            logger.debug("fact extraction failed", exc_info=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _new_session_id() -> str:
    """Lazy import to avoid pymongo import at module load."""
    try:
        from .memory.store import new_session_id
        return new_session_id()
    except Exception:
        import uuid
        return uuid.uuid4().hex


def _summarize_for_memory(llm, messages: list[dict]) -> str:
    """Produce a ≤200-word summary of this session for cross-session recall."""
    if len(messages) < 3:
        return ""
    transcript = _format_for_summary(messages[1:])
    prompt = [
        {
            "role": "system",
            "content": (
                "You summarize coding-agent sessions for persistent memory. "
                "Capture the goal, key decisions, files touched, and any open "
                "questions. Reply with plain prose only. Max 200 words."
            ),
        },
        {
            "role": "user",
            "content": (
                "Summarize this session for future recall.\n\n"
                "--- Session ---\n" + transcript
            ),
        },
    ]
    try:
        msg = llm.chat(prompt)
        return (msg.get("content") or "").strip()
    except Exception:
        return ""


def _extract_facts_for_memory(llm, messages: list[dict]) -> list[dict]:
    """Ask the LLM for 3-5 reusable facts/decisions. Returns [] on failure."""
    if len(messages) < 3:
        return []
    transcript = _format_for_summary(messages[1:])
    prompt = [
        {
            "role": "system",
            "content": (
                "Extract 3-5 REUSABLE facts or decisions from this coding "
                "session. Each item: (a) a 'kind' in {decision, fact, "
                "error_seen, snippet}, and (b) a short 'text' (max 200 chars) "
                "that would be useful in a FUTURE session in the same project. "
                "Do NOT copy verbatim file contents; summarize as principles. "
                "Reply as compact JSON: "
                '{"items":[{"kind":"decision","text":"..."},...]}'
            ),
        },
        {
            "role": "user",
            "content": "--- Session ---\n" + transcript,
        },
    ]
    try:
        msg = llm.chat(prompt)
        raw = (msg.get("content") or "").strip()
        # Try direct parse; if model added prose, find the first {...} block.
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start < 0 or end <= start:
                return []
            data = json.loads(raw[start:end + 1])
        items = data.get("items") or []
        out: list[dict] = []
        for it in items[:5]:
            if isinstance(it, dict) and it.get("text"):
                out.append({
                    "kind": str(it.get("kind") or "fact")[:32],
                    "text": str(it.get("text"))[:200],
                })
        return out
    except Exception:
        return []


def _parse_tool_call(tc: dict) -> tuple[str, dict, str]:
    """Extract (name, args, id) from an OpenAI-format tool_call dict."""
    fn = tc.get("function", {})
    name = fn.get("name", "unknown")
    raw_args = fn.get("arguments", "{}")
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except json.JSONDecodeError:
        args = {}
    tc_id = tc.get("id", "")
    return name, args, tc_id


def _fmt_args(args: dict) -> str:
    """Format tool arguments for display (truncated)."""
    parts = []
    for k, v in args.items():
        s = repr(v)
        parts.append(f"{k}={s[:50]}{'…' if len(s) > 50 else ''}")
    return ", ".join(parts)


def _print_result(result: str, print_fn: PrintFn) -> None:
    """Print a preview of a tool result (first 8 lines)."""
    lines = result.splitlines()
    preview = "\n  ".join(lines[:8])
    if len(lines) > 8:
        preview += f"\n  … ({len(lines) - 8} more lines)"
    print_fn(f"  → {preview}")


def _format_for_summary(messages: list[dict]) -> str:
    """Render a message list as plain text for the summarizer LLM.

    Strips raw ``tool_calls`` structures down to a short marker so the
    summarizer focuses on intent rather than re-emitting tool calls.
    """
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content") or ""
        tool_calls = m.get("tool_calls") or []
        if tool_calls:
            names = ", ".join(
                tc.get("function", {}).get("name", "?") for tc in tool_calls
            )
            marker = f" [called: {names}]"
        else:
            marker = ""
        lines.append(f"[{role}]{marker} {content}".rstrip())
    return "\n".join(lines)
