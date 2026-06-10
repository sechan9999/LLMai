"""Optional Google ADK entry point for LLMai.

This module is imported only by the ``google_agent`` package. The normal
CLI and Web UI keep their lightweight dependency set and local-first defaults.
"""
import os
from typing import Any

from .tools import execute_tool

DEFAULT_GOOGLE_MODEL = "gemini-3.1-pro-preview"
GITLAB_MCP_URL = "https://gitlab.com/api/v4/mcp"

_MUTATING_MCP_TERMS = {
    "add", "approve", "cancel", "close", "create", "delete", "merge",
    "post", "retry", "run", "set", "trigger", "update", "write",
}


def google_model() -> str:
    """Return the Gemini model used by the Google ADK profile."""
    return os.environ.get("LLMAI_GOOGLE_MODEL", DEFAULT_GOOGLE_MODEL)


def read_workspace_file(path: str, offset: int = 1, limit: int = 400) -> str:
    """Read a UTF-8 text file inside the configured LLMai workspace."""
    return execute_tool("read_file", {"path": path, "offset": offset, "limit": limit})


def list_workspace_files(path: str = ".", pattern: str = "**/*") -> str:
    """List files inside the configured LLMai workspace."""
    return execute_tool("list_files", {"path": path, "pattern": pattern})


def search_workspace(pattern: str, path: str = ".", include: str = "*") -> str:
    """Search text inside files in the configured LLMai workspace."""
    return execute_tool(
        "search_code", {"pattern": pattern, "path": path, "include": include},
    )


def _read_only_mcp_tool(tool: Any, _context: Any = None) -> bool:
    """Keep state-changing GitLab MCP tools out of the ADK demo profile."""
    name = str(getattr(tool, "name", tool)).lower().replace("-", "_")
    words = [word for word in name.split("_") if word]
    action = next((word for word in words if word not in {"mcp", "gitlab"}), "")
    return action not in _MUTATING_MCP_TERMS


def build_google_agent():
    """Build the Gemini + Google ADK agent with GitLab's official MCP server.

    ``google-adk`` is an optional dependency so importing the regular LLMai
    runtime never imports Google SDKs.
    """
    try:
        from google.adk.agents import LlmAgent
        from google.adk.tools.mcp_tool.mcp_toolset import (
            MCPToolset,
            StdioConnectionParams,
        )
        from mcp import StdioServerParameters
    except ImportError as exc:
        raise RuntimeError(
            'Google ADK support is optional. Install it with: pip install -e ".[google-cloud]"'
        ) from exc

    gitlab = MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=["-y", "mcp-remote", GITLAB_MCP_URL],
            ),
        ),
        tool_filter=_read_only_mcp_tool,
    )

    return LlmAgent(
        name="llmai_gitlab_agent",
        model=google_model(),
        description="Read-only coding investigation agent for local workspaces and GitLab.",
        instruction=(
            "You are LLMai running through Google Agent Development Kit. "
            "Investigate coding tasks by reading the local workspace and using "
            "GitLab's official MCP tools. Plan multi-step work, cite the files and "
            "GitLab objects you inspected, and clearly label proposed changes. "
            "This profile is read-only: do not claim to edit files, execute shell "
            "commands, or mutate GitLab state."
        ),
        tools=[read_workspace_file, list_workspace_files, search_workspace, gitlab],
    )
