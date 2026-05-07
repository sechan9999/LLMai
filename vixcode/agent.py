"""
AgentLoop: observe → judge → act × while(True)

This is the core difference from a chatbot.
A chatbot: one input → one output.
An agent:  one input → loop until goal reached.
"""
import json
from typing import Callable
from .llm import OllamaClient
from .tools import TOOL_DEFINITIONS, execute_tool
from .permissions import PermissionManager


SYSTEM_PROMPT = """You are an expert coding assistant running locally. Help the user with software development tasks.

You have tools for reading/writing files, running shell commands, and searching code. Work methodically:
- Read files before modifying them
- Verify your changes are correct
- Run tests when appropriate
- Be concise; stop and summarize when the task is done

Always read a file before editing it to get the exact content."""


PrintFn = Callable[..., None]


class AgentLoop:
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

    # ── Public ──────────────────────────────────────────────────────────────
    def run(self, user_input: str, print_fn: PrintFn = print) -> str:
        self.messages.append({"role": "user", "content": user_input})
        last_text = ""

        for iteration in range(self.max_iterations):
            # ── 1. Call LLM ─────────────────────────────────────────────────
            try:
                msg = self.llm.chat(self.messages, tools=TOOL_DEFINITIONS)
            except Exception as e:
                print_fn(f"\n[LLM error] {e}")
                break

            content = msg.get("content") or ""
            tool_calls = msg.get("tool_calls") or []

            # ── 2. Print text response ───────────────────────────────────────
            if content:
                print_fn(f"\n{content}")
                last_text = content

            # ── 3. Add assistant message to history ──────────────────────────
            assistant_msg: dict = {"role": "assistant"}
            if content:
                assistant_msg["content"] = content
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            self.messages.append(assistant_msg)

            # ── 4. No tool calls → done ──────────────────────────────────────
            if not tool_calls:
                break

            # ── 5. Execute each tool call (observe → act) ────────────────────
            for tc in tool_calls:
                fn_name, fn_args, tc_id = _parse_tool_call(tc)
                print_fn(f"\n  ⚙  {fn_name}({_fmt_args(fn_args)})")

                if self.permissions.check(fn_name, fn_args):
                    result = execute_tool(fn_name, fn_args)
                    _print_result(result, print_fn)
                else:
                    result = f"Permission denied for {fn_name}"
                    print_fn(f"  ✗  {result}")

                # Feed result back into context (observe)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result,
                })

        return last_text

    def reset(self):
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    @property
    def token_estimate(self) -> int:
        total = sum(len(m.get("content", "")) for m in self.messages)
        return total // 4  # rough estimate: 4 chars ≈ 1 token

    def maybe_compress(self, threshold: int = 50_000):
        """Summarise old messages when context gets large."""
        if self.token_estimate < threshold:
            return
        # Keep system + last 6 turns; summarise the rest
        keep_recent = 6
        system = self.messages[:1]
        old = self.messages[1:-keep_recent]
        recent = self.messages[-keep_recent:]
        summary_prompt = (
            "Summarise the key decisions, file changes, and conclusions from "
            "this conversation in ≤200 words."
        )
        try:
            summary_msg = self.llm.chat(
                old + [{"role": "user", "content": summary_prompt}]
            )
            summary = summary_msg.get("content", "(summary unavailable)")
        except Exception:
            summary = "(context compressed)"

        self.messages = system + [
            {"role": "system", "content": f"[Earlier context summary]\n{summary}"}
        ] + recent


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_tool_call(tc: dict) -> tuple[str, dict, str]:
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
    parts = []
    for k, v in args.items():
        s = repr(v)
        parts.append(f"{k}={s[:50]}{'…' if len(s) > 50 else ''}")
    return ", ".join(parts)


def _print_result(result: str, print_fn: PrintFn):
    lines = result.splitlines()
    preview = "\n  ".join(lines[:8])
    if len(lines) > 8:
        preview += f"\n  … ({len(lines) - 8} more lines)"
    print_fn(f"  → {preview}")
