"""Unit tests for llmai.mcp.registry — pure logic, no MCP SDK required."""
from types import SimpleNamespace

from llmai.mcp.registry import (
    MAX_RESULT_CHARS,
    McpRegistry,
    flatten_result,
    qualify,
    sanitize,
)


class TestNaming:
    def test_sanitize_dashes_and_dots(self):
        # dash is allowed by the OpenAI charset; dots and spaces are not
        assert sanitize("list-collections") == "list-collections"
        assert sanitize("a.b.c") == "a_b_c"
        assert sanitize("tool name!") == "tool_name_"

    def test_qualify_basic(self):
        assert qualify("mongodb", "find", set()) == "mcp__mongodb__find"

    def test_qualify_collision_gets_suffix(self):
        taken = {"mcp__srv__tool"}
        assert qualify("srv", "tool", taken) == "mcp__srv__tool_2"
        taken.add("mcp__srv__tool_2")
        assert qualify("srv", "tool", taken) == "mcp__srv__tool_3"

    def test_qualify_truncates_to_64_chars(self):
        long_tool = "x" * 100
        name = qualify("server", long_tool, set())
        assert len(name) <= 64
        assert name.startswith("mcp__server__")

    def test_qualify_truncated_collision_stays_within_limit(self):
        long_tool = "x" * 100
        first = qualify("server", long_tool, set())
        second = qualify("server", long_tool, {first})
        assert len(second) <= 64
        assert second != first
        assert second.endswith("_2")


class TestRegistry:
    def test_openai_format(self):
        reg = McpRegistry(call_fn=lambda s, t, a: "")
        specs = reg.add_server_tools(
            "mongodb", [("find", "Query documents", {"type": "object"})]
        )
        fmt = specs[0].to_openai_format()
        assert fmt["type"] == "function"
        assert fmt["function"]["name"] == "mcp__mongodb__find"
        assert fmt["function"]["description"].startswith("[MCP:mongodb]")
        assert fmt["function"]["parameters"] == {"type": "object"}

    def test_empty_schema_gets_object_default(self):
        reg = McpRegistry(call_fn=lambda s, t, a: "")
        specs = reg.add_server_tools("srv", [("t", "", {})])
        fmt = specs[0].to_openai_format()
        assert fmt["function"]["parameters"]["type"] == "object"

    def test_handler_routes_to_call_fn(self):
        calls = []
        reg = McpRegistry(call_fn=lambda s, t, a: calls.append((s, t, a)) or "ok")
        reg.add_server_tools("srv", [("echo", "", {})])
        [(spec, handler)] = reg.get_registrations()
        assert handler(text="hi") == "ok"
        assert calls == [("srv", "echo", {"text": "hi"})]

    def test_cross_server_collision(self):
        reg = McpRegistry(call_fn=lambda s, t, a: "")
        reg.add_server_tools("a", [("run", "", {})])
        specs = reg.add_server_tools("a", [("run", "", {})])
        assert specs[0].qualified == "mcp__a__run_2"


def _result(blocks, is_error=False):
    return SimpleNamespace(content=blocks, isError=is_error)


class TestFlattenResult:
    def test_text_blocks_joined(self):
        r = _result([
            SimpleNamespace(type="text", text="line1"),
            SimpleNamespace(type="text", text="line2"),
        ])
        assert flatten_result(r) == "line1\nline2"

    def test_is_error_prefixed(self):
        r = _result([SimpleNamespace(type="text", text="boom")], is_error=True)
        assert flatten_result(r).startswith("Error from MCP server:")

    def test_image_omitted(self):
        r = _result([SimpleNamespace(type="image", mimeType="image/png", data="A" * 10)])
        out = flatten_result(r)
        assert "image content omitted" in out
        assert "image/png" in out

    def test_empty_result(self):
        assert flatten_result(_result([])) == "(empty result)"

    def test_truncation(self):
        r = _result([SimpleNamespace(type="text", text="z" * (MAX_RESULT_CHARS + 100))])
        out = flatten_result(r)
        assert out.endswith("…[truncated]")
        assert len(out) < MAX_RESULT_CHARS + 50
