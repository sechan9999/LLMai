"""
Async agent loop for WebSocket.
Supports two tool-calling modes:
  - native:  OpenAI-compatible tools param (qwen2.5-coder, llama3.1, etc.)
  - xml:     Model outputs <tool_call> tags in text; we parse them
             (fallback for gemma3, phi3, mistral, etc.)
"""
import asyncio
import json
import re
import httpx
from fastapi import WebSocket

from vixcode.tools import TOOL_DEFINITIONS, execute_tool
from vixcode.permissions import DEFAULT, _preview

# ── Tool descriptions injected into system prompt for XML mode ────────────────
def _tool_docs() -> str:
    lines = []
    for td in TOOL_DEFINITIONS:
        fn = td["function"]
        params = fn["parameters"].get("properties", {})
        req    = fn["parameters"].get("required", [])
        args   = ", ".join(
            f"{k}{'*' if k in req else '?'}: {v.get('type','str')}"
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
    base = model.split(":")[0].lower()
    return any(base.startswith(m) for m in NATIVE_TOOL_MODELS)


class WebSocketAgent:
    def __init__(self, llm_url: str, model: str, ws: WebSocket):
        self.llm_url = llm_url.rstrip("/") + "/v1/chat/completions"
        self.model = model
        self.ws = ws
        self.native = _supports_native_tools(model)
        system = NATIVE_SYSTEM_PROMPT if self.native else XML_SYSTEM_PROMPT
        self.messages: list[dict] = [{"role": "system", "content": system}]
        self.rules: dict[str, str] = dict(DEFAULT)
        self._perm_queue: asyncio.Queue[bool] = asyncio.Queue()

    # ── Public ───────────────────────────────────────────────────────────────

    async def run(self, user_input: str):
        self.messages.append({"role": "user", "content": user_input})

        for _ in range(20):
            try:
                msg = await self._chat()
            except Exception as e:
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

    async def handle_permission(self, approved: bool):
        await self._perm_queue.put(approved)

    def reset(self):
        system = NATIVE_SYSTEM_PROMPT if self.native else XML_SYSTEM_PROMPT
        self.messages = [{"role": "system", "content": system}]

    # ── Native tool-call mode ────────────────────────────────────────────────

    async def _handle_native(self, msg: dict):
        content    = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []

        if content:
            await self._send("text", content=content)

        assistant: dict = {"role": "assistant"}
        if content:    assistant["content"] = content
        if tool_calls: assistant["tool_calls"] = tool_calls
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
            await self._send("error", message=str(e))
            return
        await self._handle_native(next_msg)

    # ── XML text-parsing mode ────────────────────────────────────────────────

    async def _handle_xml(self, msg: dict) -> bool:
        """Returns True when the agent is done (no more tool calls)."""
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
                "content": f"<tool_result>\n{self._last_result}\n</tool_result>"
            })

        return False  # continue loop

    # ── Shared tool execution ────────────────────────────────────────────────

    async def _exec_tool(self, fn_name: str, fn_args: dict):
        await self._send("tool_start", name=fn_name, args=fn_args)
        approved = await self._check_perm(fn_name, fn_args)

        if approved:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, execute_tool, fn_name, fn_args)
            error = False
        else:
            result = f"Permission denied for {fn_name}"
            error = True

        self._last_result = result
        await self._send("tool_result", name=fn_name, content=result[:4000], error=error)

    async def _check_perm(self, tool_name: str, args: dict) -> bool:
        mode = self.rules.get(tool_name, "ask")
        if mode == "allow": return True
        if mode == "deny":  return False
        await self._send(
            "permission_request",
            tool=tool_name,
            preview=_preview(tool_name, args),
            args=args,
        )
        return await self._perm_queue.get()

    async def _chat(self) -> dict:
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

    async def _send(self, msg_type: str, **kwargs):
        await self.ws.send_json({"type": msg_type, **kwargs})


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_native_tc(tc: dict) -> tuple[str, dict, str]:
    fn   = tc.get("function", {})
    name = fn.get("name", "unknown")
    raw  = fn.get("arguments", "{}")
    try:
        args = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except json.JSONDecodeError:
        args = {}
    return name, args, tc.get("id", "")


_XML_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)

def _extract_xml_calls(text: str) -> list[tuple[str, dict]]:
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
