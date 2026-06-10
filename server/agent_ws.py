"""
Async agent loop for WebSocket.

Supports two tool-calling modes:
  - native:  OpenAI-compatible tools param (qwen2.5-coder, llama3.1, etc.)
  - xml:     Model outputs <tool_call> tags in text; we parse them
             (fallback for gemma3, phi3, mistral, etc.)
"""
import asyncio
import json
import logging
import re
import time

import httpx
from fastapi import WebSocket

from llmai import memory, telemetry
from llmai.permissions import DEFAULT, _preview
from llmai.tools import TOOL_DEFINITIONS, WORKSPACE_ROOT, execute_tool

logger = logging.getLogger(__name__)


# ── Tool descriptions injected into system prompt for XML mode ────────────────

def _tool_docs() -> str:
    """Build a plain-text tool reference for injection into the XML system prompt."""
    lines = []
    for td in TOOL_DEFINITIONS:
        fn = td["function"]
        params = fn["parameters"].get("properties", {})
        req = fn["parameters"].get("required", [])
        args = ", ".join(
            f"{k}{'*' if k in req else '?'}: {v.get('type', 'str')}"
            for k, v in params.items()
        )
        lines.append(f"- {fn['name']}({args}): {fn['description']}")
    return "\n".join(lines)


XML_SYSTEM_PROMPT = f"""You are an expert coding assistant. Help the user with software tasks.

You have these tools. To call a tool, output EXACTLY this format (no extra text around it):
<tool_call>
{{"name": "tool_name", "args": {{"param": "value"}}}}
</tool_call>

Available tools:
{_tool_docs()}

Rules:
- Read files before editing them
- After calling a tool you will receive <tool_result>…</tool_result> — use it to continue
- When done, summarise what you did
- Never make up file contents; always read first
- If `search_knowledge` is available, call it before writing code that touches
  an error path or external API. If `recall_memory` is available, use it when
  the task feels familiar from a prior session.
"""

NATIVE_SYSTEM_PROMPT = (
    "You are an expert coding assistant running locally. "
    "Help with software development tasks.\n"
    "Use tools methodically: read before edit, verify after write, "
    "run tests when appropriate. Be concise.\n"
    "If `search_knowledge` is available, call it BEFORE writing code "
    "that touches an error path or external API.\n"
    "If `recall_memory` is available, use it when the task feels "
    "familiar from a prior session."
)


# ── Models known to support native tool calling ───────────────────────────────

NATIVE_TOOL_MODELS = {
    "qwen2.5", "qwen2.5-coder", "qwen3",
    "llama3.1", "llama3.2", "llama3.3",
    "mistral-nemo", "firefunction",
    "command-r", "command-r-plus",
}


def _supports_native_tools(model: str) -> bool:
    """Check if *model* supports OpenAI-compatible function calling."""
    base = model.split(":")[0].lower()
    return any(base.startswith(m) for m in NATIVE_TOOL_MODELS)


class WebSocketAgent:
    """Async agentic loop communicating over a WebSocket.

    Handles both native tool-calling and XML fallback modes depending
    on the model.  Permissions are checked before each tool execution.
    """

    MAX_ITERATIONS = 20

    def __init__(
        self,
        llm_url: str,
        model: str,
        ws: WebSocket,
        *,
        chat_path: str = "/v1/chat/completions",
        headers: dict[str, str] | None = None,
        provider: str = "ollama",
    ):
        self.llm_url = llm_url.rstrip("/") + chat_path
        self.model = model
        self.ws = ws
        self.headers: dict[str, str] = dict(headers or {})
        self.provider = provider
        # Cloud-hosted models (Gemini etc.) almost always support native
        # tool calling; only Ollama needs the per-model gate.
        self.native = (provider != "ollama") or _supports_native_tools(model)
        system = NATIVE_SYSTEM_PROMPT if self.native else XML_SYSTEM_PROMPT
        self.messages: list[dict] = [{"role": "system", "content": system}]
        # MCP tool permissions are discovered at server startup (mcp.init),
        # after this module's import — merge them per-connection.
        from llmai import mcp as _mcp
        self.rules: dict[str, str] = {**DEFAULT, **_mcp.MCP_DEFAULT_PERMISSIONS}
        self._perm_queue: asyncio.Queue[bool] = asyncio.Queue()
        self._last_result: str = ""
        self.session_id: str = _new_session_id()
        self.turn_count: int = 0
        self._memory_primed: bool = False

    # ── Public ───────────────────────────────────────────────────────────────

    async def run(self, user_input: str) -> None:
        """Execute one full agent turn for *user_input*.

        Iterates the model/tool loop up to ``MAX_ITERATIONS`` times for both
        native and XML modes. Each handler returns ``True`` when the agent has
        produced a final response with no more tool calls.

        Native mode streams text content to the client as it arrives; XML
        mode waits for the full response so ``<tool_call>`` tags can be
        parsed cleanly before display.
        """
        await self._prime_memory()
        self.messages.append({"role": "user", "content": user_input})
        self.turn_count += 1

        with telemetry.turn_span(
            mode="ws-native" if self.native else "ws-xml",
            provider=self.provider,
            model=self.model,
            input_chars=len(user_input),
        ) as turn:
            iterations_done = 0
            for i in range(self.MAX_ITERATIONS):
                iterations_done = i + 1
                with telemetry.iteration_span(
                    number=i + 1,
                    tokens_estimate=telemetry.estimate_tokens(self.messages),
                ):
                    try:
                        with telemetry.llm_span(
                            model=self.model,
                            provider=self.provider,
                            message_count=len(self.messages),
                            streamed=self.native,
                        ) as llm_s:
                            tokens_in = telemetry.estimate_tokens(self.messages)
                            if self.native:
                                msg = await self._chat_stream_native()
                            else:
                                msg = await self._chat()
                            telemetry.record_tokens(
                                direction="in", count=tokens_in, model=self.model,
                            )
                            out_chars = len((msg.get("content") or ""))
                            telemetry.record_tokens(
                                direction="out", count=out_chars // 4, model=self.model,
                            )
                            llm_s.set_attribute(
                                "llm.tool_calls.requested",
                                len(msg.get("tool_calls") or []),
                            )
                    except Exception as e:
                        logger.exception("LLM call failed")
                        await self._send("error", message=str(e))
                        return

                    if self.native:
                        done = await self._handle_native(msg, streamed=True)
                    else:
                        done = await self._handle_xml(msg)

                    if done:
                        turn.set_attribute("agent.iterations.actual", iterations_done)
                        await self._persist_turn()
                        return

            turn.set_attribute("agent.iterations.actual", iterations_done)
            await self._persist_turn()
            await self._send(
                "error",
                message=f"Reached max iterations ({self.MAX_ITERATIONS}) without a final answer.",
            )
            await self._send("done")

    async def handle_permission(self, approved: bool) -> None:
        """Receive the user's permission decision from the UI."""
        await self._perm_queue.put(approved)

    def reset(self) -> None:
        """Clear conversation context."""
        # Fire-and-forget session finalize — extracts summary + facts.
        try:
            asyncio.create_task(self._finalize_session())
        except RuntimeError:
            pass  # no running loop (e.g. shutdown); skip
        system = NATIVE_SYSTEM_PROMPT if self.native else XML_SYSTEM_PROMPT
        self.messages = [{"role": "system", "content": system}]
        self.session_id = _new_session_id()
        self.turn_count = 0
        self._memory_primed = False

    # ── Native tool-call mode ────────────────────────────────────────────────

    async def _handle_native(self, msg: dict, *, streamed: bool = False) -> bool:
        """Process one response that may contain native tool_calls.

        Args:
            msg: Assembled assistant message ``{content, tool_calls}``.
            streamed: True when content was already emitted as ``text``
                deltas during streaming — we then skip re-sending it.

        Returns:
            True when the agent has produced a final answer (no tool calls),
            False when tools were executed and another iteration is needed.
        """
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []

        if content and not streamed:
            await self._send("text", content=content)

        assistant: dict = {"role": "assistant"}
        if content:
            assistant["content"] = content
        if tool_calls:
            assistant["tool_calls"] = tool_calls
        self.messages.append(assistant)

        if not tool_calls:
            await self._send("done")
            return True

        for tc in tool_calls:
            fn_name, fn_args, tc_id = _parse_native_tc(tc)
            await self._exec_tool(fn_name, fn_args)
            self.messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": self._last_result,
            })

        return False  # continue loop in run()

    # ── XML text-parsing mode ────────────────────────────────────────────────

    async def _handle_xml(self, msg: dict) -> bool:
        """Process XML-style tool calls from model text output.

        Returns True when the agent is done (no more tool calls).
        """
        raw = msg.get("content") or ""
        self.messages.append({"role": "assistant", "content": raw})

        calls = _extract_xml_calls(raw)

        # Text before first tool call
        text_before = raw.split("<tool_call>")[0].strip()
        if text_before:
            await self._send("text", content=text_before)

        if not calls:
            await self._send("done")
            return True

        for fn_name, fn_args in calls:
            await self._exec_tool(fn_name, fn_args)
            self.messages.append({
                "role": "user",
                "content": f"<tool_result>\n{self._last_result}\n</tool_result>",
            })

        return False  # continue loop

    # ── Shared tool execution ────────────────────────────────────────────────

    async def _exec_tool(self, fn_name: str, fn_args: dict) -> None:
        """Execute a single tool call with permission checking."""
        await self._send("tool_start", name=fn_name, args=fn_args)

        with telemetry.tool_span(name=fn_name, args=fn_args) as (_, oc):
            mode = self.rules.get(fn_name, "ask")
            perm_start = time.monotonic()
            try:
                approved = await self._check_perm(fn_name, fn_args)
            except Exception as e:
                logger.warning("Permission check error for %s: %s", fn_name, e)
                approved = False
            oc.perm_latency_ms = (time.monotonic() - perm_start) * 1000

            if approved:
                oc.permission = "allow" if mode == "allow" else "ask_allow"
                loop = asyncio.get_event_loop()
                try:
                    result = await loop.run_in_executor(
                        None, execute_tool, fn_name, fn_args,
                    )
                    if result.startswith("Error"):
                        oc.error = True
                except Exception as e:
                    result = f"Error: Tool execution failed: {e}"
                    oc.error = True
                error = oc.error
            else:
                oc.permission = "deny" if mode == "deny" else "ask_deny"
                oc.error = True
                result = f"Permission denied for {fn_name}"
                error = True

            oc.result_chars = len(result)

        self._last_result = result
        await self._send("tool_result", name=fn_name, content=result[:4000], error=error)

    async def _check_perm(self, tool_name: str, args: dict) -> bool:
        """Check permission for a tool, potentially waiting for user input."""
        mode = self.rules.get(tool_name, "ask")
        if mode == "allow":
            return True
        if mode == "deny":
            return False
        await self._send(
            "permission_request",
            tool=tool_name,
            preview=_preview(tool_name, args),
            args=args,
        )
        return await self._perm_queue.get()

    async def _chat(self) -> dict:
        """Send a non-streaming chat completion request to Ollama.

        Used by XML mode (where we need the full text before parsing
        ``<tool_call>`` tags). Retries up to twice on transient errors.
        """
        payload: dict = {
            "model": self.model,
            "messages": self.messages,
            "stream": False,
        }
        if self.native:
            payload["tools"] = TOOL_DEFINITIONS

        backoff = 0.5
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=180, headers=self.headers) as client:
                    resp = await client.post(self.llm_url, json=payload)
                    resp.raise_for_status()
                    return resp.json()["choices"][0]["message"]
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                if attempt == 2:
                    raise
                logger.warning(
                    "Ollama _chat failed (attempt %d/3): %s — retrying in %.1fs",
                    attempt + 1, exc, backoff,
                )
                await asyncio.sleep(backoff)
                backoff *= 2
        raise last_exc  # pragma: no cover

    async def _chat_stream_native(self) -> dict:
        """Stream a chat completion in OpenAI-compat mode and emit deltas.

        Sends a ``text`` event for each content chunk as it arrives, and
        accumulates ``tool_calls`` deltas (merged by index) for return.
        Falls back transparently to a single non-streaming call if the
        Ollama server doesn't support streaming for this model.

        Returns:
            ``{"content": str | None, "tool_calls": list[dict] | None}``
        """
        payload = {
            "model": self.model,
            "messages": self.messages,
            "tools": TOOL_DEFINITIONS,
            "stream": True,
        }

        content_parts: list[str] = []
        tool_calls: dict[int, dict] = {}

        try:
            async with httpx.AsyncClient(timeout=180, headers=self.headers) as client:
                async with client.stream("POST", self.llm_url, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        line = line.strip()
                        if line == "data: [DONE]" or not line.startswith("data: "):
                            continue
                        try:
                            chunk = json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue
                        choice = (chunk.get("choices") or [{}])[0]
                        delta = choice.get("delta") or {}

                        text = delta.get("content")
                        if text:
                            content_parts.append(text)
                            await self._send("text", content=text)

                        for tc_delta in (delta.get("tool_calls") or []):
                            idx = tc_delta.get("index", 0)
                            cur = tool_calls.setdefault(idx, {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            })
                            if tc_delta.get("id"):
                                cur["id"] = tc_delta["id"]
                            if tc_delta.get("type"):
                                cur["type"] = tc_delta["type"]
                            fn_delta = tc_delta.get("function") or {}
                            if fn_delta.get("name"):
                                cur["function"]["name"] += fn_delta["name"]
                            if fn_delta.get("arguments") is not None:
                                cur["function"]["arguments"] += fn_delta.get("arguments", "")
        except httpx.HTTPStatusError as exc:
            # Some Ollama builds don't support streaming with tools — retry non-streaming.
            logger.warning("Streaming failed (%s); falling back to non-streaming", exc)
            return await self._chat()

        return {
            "content": "".join(content_parts) or None,
            "tool_calls": list(tool_calls.values()) if tool_calls else None,
        }

    async def _send(self, msg_type: str, **kwargs) -> None:
        """Send a typed JSON message over the WebSocket."""
        await self.ws.send_json({"type": msg_type, **kwargs})

    # ── Memory hooks (best-effort; never raise into the loop) ────────────────

    async def _prime_memory(self) -> None:
        """Inject prior-session summaries + active skills as system messages."""
        if self._memory_primed:
            return
        self._memory_primed = True
        store = memory.get_store()
        if store is None:
            return
        loop = asyncio.get_event_loop()

        # Summaries
        try:
            summaries = await loop.run_in_executor(
                None, store.recent_summaries, str(WORKSPACE_ROOT),
            )
        except Exception:
            logger.debug("recent_summaries failed", exc_info=True)
            summaries = []
        if summaries:
            lines = ["[Memory from prior sessions in this workspace]"]
            for s in summaries:
                when = s.get("created_at")
                when_str = when.strftime("%Y-%m-%d") if when else "?"
                text = (s.get("summary") or "").strip()
                if text:
                    lines.append(f"• ({when_str}) {text}")
            if len(lines) > 1:
                self.messages.insert(1, {"role": "system", "content": "\n".join(lines)})

        # Skills
        try:
            skills = await loop.run_in_executor(
                None,
                lambda: store.list_skills(str(WORKSPACE_ROOT),
                                          limit=store.skill_inject_limit),
            )
        except Exception:
            logger.debug("list_skills failed", exc_info=True)
            return
        if not skills:
            return
        from llmai.memory.skills import format_skills_message
        block = format_skills_message(skills)
        if not block:
            return
        insert_at = 2 if summaries else 1
        self.messages.insert(insert_at, {"role": "system", "content": block})
        try:
            await loop.run_in_executor(
                None,
                lambda: store.bump_skill_usage(
                    str(WORKSPACE_ROOT),
                    [s.get("name") for s in skills if s.get("name")],
                ),
            )
        except Exception:
            logger.debug("bump_skill_usage failed", exc_info=True)

    async def _persist_turn(self) -> None:
        store = memory.get_store()
        if store is None:
            return
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: store.save_session(
                    session_id=self.session_id,
                    workspace_path=str(WORKSPACE_ROOT),
                    provider=self.provider,
                    model=self.model,
                    messages=self.messages,
                    token_estimate=telemetry.estimate_tokens(self.messages),
                    turn_count=self.turn_count,
                ),
            )
        except Exception:
            logger.debug("save_session failed", exc_info=True)

    async def _finalize_session(self) -> None:
        store = memory.get_store()
        if store is None or self.turn_count == 0:
            return
        loop = asyncio.get_event_loop()
        msgs_snapshot = list(self.messages)
        sid = self.session_id
        provider = self.provider
        model = self.model
        token_est = telemetry.estimate_tokens(msgs_snapshot)
        try:
            await loop.run_in_executor(
                None,
                lambda: store.save_session(
                    session_id=sid,
                    workspace_path=str(WORKSPACE_ROOT),
                    provider=provider,
                    model=model,
                    messages=msgs_snapshot,
                    token_estimate=token_est,
                    turn_count=self.turn_count,
                    ended=True,
                ),
            )
        except Exception:
            logger.debug("session finalize save failed", exc_info=True)

        # Best-effort summary + knowledge extraction. Runs in executor so the
        # synchronous LLM call doesn't block the event loop.
        try:
            summary = await loop.run_in_executor(
                None, _summarize_via_llm, self, msgs_snapshot,
            )
            if summary:
                await loop.run_in_executor(
                    None,
                    lambda: store.save_summary(
                        session_id=sid,
                        workspace_path=str(WORKSPACE_ROOT),
                        summary=summary,
                        source_token_count=token_est,
                    ),
                )
        except Exception:
            logger.debug("summary extraction failed", exc_info=True)

        try:
            facts = await loop.run_in_executor(
                None, _extract_facts_via_llm, self, msgs_snapshot,
            )
            if facts:
                await loop.run_in_executor(
                    None,
                    lambda: store.save_knowledge(
                        workspace_path=str(WORKSPACE_ROOT),
                        source_session_id=sid,
                        items=facts,
                    ),
                )
        except Exception:
            logger.debug("fact extraction failed", exc_info=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_native_tc(tc: dict) -> tuple[str, dict, str]:
    """Parse an OpenAI-format tool_call into (name, args, id)."""
    fn = tc.get("function", {})
    name = fn.get("name", "unknown")
    raw = fn.get("arguments", "{}")
    try:
        args = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except json.JSONDecodeError:
        args = {}
    return name, args, tc.get("id", "")


_XML_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def _extract_xml_calls(text: str) -> list[tuple[str, dict]]:
    """Extract tool calls from XML-tagged text."""
    results = []
    for m in _XML_RE.finditer(text):
        try:
            obj = json.loads(m.group(1))
            name = obj.get("name", "")
            args = obj.get("args", obj.get("arguments", {}))
            if name:
                results.append((name, args))
        except json.JSONDecodeError:
            continue
    return results


def _new_session_id() -> str:
    try:
        from llmai.memory.store import new_session_id
        return new_session_id()
    except Exception:
        import uuid
        return uuid.uuid4().hex


def _format_session_for_summary(messages: list[dict]) -> str:
    """Render a message list as plain text for the summarizer LLM."""
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content") or ""
        tool_calls = m.get("tool_calls") or []
        if tool_calls:
            names = ", ".join(
                tc.get("function", {}).get("name", "?") for tc in tool_calls
            )
            lines.append(f"[{role} called: {names}] {content}".rstrip())
        else:
            lines.append(f"[{role}] {content}".rstrip())
    return "\n".join(lines)


def _llm_once(agent: "WebSocketAgent", prompt_messages: list[dict]) -> str:
    """One-shot non-streaming LLM call over the agent's configured endpoint.

    Used by the session-finalize path so we don't bring an OllamaClient
    dependency into the async loop just for two end-of-session calls.
    Synchronous httpx.Client — runs inside ``run_in_executor``.
    """
    import httpx
    payload = {
        "model": agent.model,
        "messages": prompt_messages,
        "stream": False,
    }
    try:
        with httpx.Client(timeout=60, headers=agent.headers) as client:
            resp = client.post(agent.llm_url, json=payload)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"].get("content", "") or ""
    except Exception:
        return ""


def _summarize_via_llm(agent: "WebSocketAgent", messages: list[dict]) -> str:
    if len(messages) < 3:
        return ""
    transcript = _format_session_for_summary(messages[1:])
    out = _llm_once(agent, [
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
    ])
    return out.strip()


def _extract_facts_via_llm(agent: "WebSocketAgent", messages: list[dict]) -> list[dict]:
    if len(messages) < 3:
        return []
    transcript = _format_session_for_summary(messages[1:])
    raw = _llm_once(agent, [
        {
            "role": "system",
            "content": (
                "Extract 3-5 REUSABLE facts or decisions from this coding "
                "session. Each item: 'kind' in {decision, fact, error_seen, "
                "snippet}, and a short 'text' (max 200 chars) useful in a "
                "FUTURE session in the same project. Do NOT copy verbatim "
                "file contents. Reply as compact JSON: "
                '{"items":[{"kind":"decision","text":"..."},...]}'
            ),
        },
        {"role": "user", "content": "--- Session ---\n" + transcript},
    ])
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return []
        try:
            data = json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return []
    items = data.get("items") or []
    out: list[dict] = []
    for it in items[:5]:
        if isinstance(it, dict) and it.get("text"):
            out.append({
                "kind": str(it.get("kind") or "fact")[:32],
                "text": str(it.get("text"))[:200],
            })
    return out
