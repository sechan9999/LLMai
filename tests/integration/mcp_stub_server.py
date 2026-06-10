"""
Minimal MCP server for integration tests.

Speaks MCP over stdio using the official SDK's FastMCP helper — no Node,
no live backends. Launched by test_mcp_e2e.py as:

    python tests/integration/mcp_stub_server.py
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("llmai-stub")


@mcp.tool()
def echo(text: str) -> str:
    """Echo the input back."""
    return f"echo: {text}"


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
