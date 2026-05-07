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

import httpx
from fastapi import WebSocket

from vixcode.tools import TOOL_DEFINITIONS, execute_tool
from vixcode.permissions import DEFAULT, _preview

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
"""

NATIVE_SYSTEM_PROMPT = """You are an expert coding assistant running locally. Help with software development tasks.
Use tools methodically: read before edit, verify after write, run tests when appropriate. Be concise."""


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

    def __init__(self, llm_url: str, model: str, ws: WebSocket):
        self.llm_url = llm_url.rstrip("/") + "/v1/chat/completions"
        self.model = model
        self.ws = ws
        self.native = _supports_native_tools(model)
        system = NATIVE_SYSTEM_PROMPT if self.native else XML_SYSTEM_PROMPT
        self.messages: list[dict] = [{"role": "system", "content": system}]
        self.rules: dict[str, str] = dict(DEFAULT)
        self._perm_queue: asyncio.Queue[bool] = asyncio.Queue()
        self._last_result: str = ""

    # ── Public ───────────────────────────────────────────────────────────────

    async def run(self, user_input: str) -> None:
        """Execute one full agent turn for *user_input*."""
        self.messages.append({"role": "user", "content": user_input})

        for _ in range(20):
            try:
                msg = await self._chat()
            except Exception as e:
                logger.exception("LLM call failed")
                await self._send("error", message=str(e))
                return

            if self.native:
                await self._handle_native(msg)
                # native: loop continues inside _handle_native chain
                return
            else:
                done = await self._handle_xml(msg)
                if done:
                    return

        await self._send("done")

    async def handle_permission(self, approved: bool) -> None:
        """Receive the user's permission decision from the UI."""
        await self._perm_queue.put(approved)

    def reset(self) -> None:
        """Clear conversation context."""
        system = NATIVE_SYSTEM_PROMPT if self.native else XML_SYSTEM_PROMPT
        self.messages = [{"role": "system", "content": system}]

    # ── Native tool-call mode ────────────────────────────────────────────────

    async def _handle_native(self, msg: dict) -> None:
        """Process a response that may contain native tool_calls."""
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []

        if content:
            await self._send("text", content=content)

        assistant: dict = {"role": "assistant"}
        if content:
            assistant["content"] = content
        if tool_calls:
            assistant["tool_calls"] = tool_calls
        self.messages.append(assistant)

        if not tool_calls:
            await self._send("done")
            return

        for tc in tool_calls:
            fn_name, fn_args, tc_id = _parse_native_tc(tc)
            await self._exec_tool(fn_name, fn_args)
            self.messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": self._last_result,
            })

        # Continue the loop
        try:
            next_msg = await self._chat()
        except Exception as e:
            logger.exception("LLM follow-up call failed")
            await self._send("error", message=str(e))
            return
        await self._handle_native(next_msg)

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

        try:
            approved = await self._check_perm(fn_name, fn_args)
        except Exception as e:
            logger.warning("Permission check error for %s: %s", fn_name, e)
            approved = False

        if approved:
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(None, execute_tool, fn_name, fn_args)
            except Exception as e:
                result = f"Error: Tool execution failed: {e}"
            error = False
        else:
            result = f"Permission denied for {fn_name}"
            error = True

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
        """Send a chat completion request to Ollama."""
        payload: dict = {
            "model": self.model,
            "messages": self.messages,
            "stream": False,
        }
        if self.native:
            payload["tools"] = TOOL_DEFINITIONS

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(self.llm_url, json=payload)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]

    async def _send(self, msg_type: str, **kwargs) -> None:
        """Send a typed JSON message over the WebSocket."""
        await self.ws.send_json({"type": msg_type, **kwargs})


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
