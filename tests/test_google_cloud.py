"""Tests for the dependency-light parts of the Google ADK adapter."""

from llmai.google_cloud import (
    DEFAULT_GOOGLE_MODEL,
    GITLAB_MCP_URL,
    _read_only_mcp_tool,
    google_model,
)


class _Tool:
    def __init__(self, name: str):
        self.name = name


def test_google_model_defaults_to_gemini_3(monkeypatch):
    monkeypatch.delenv("LLMAI_GOOGLE_MODEL", raising=False)
    assert google_model() == DEFAULT_GOOGLE_MODEL
    assert google_model().startswith("gemini-3")


def test_google_model_can_be_overridden(monkeypatch):
    monkeypatch.setenv("LLMAI_GOOGLE_MODEL", "gemini-3-flash")
    assert google_model() == "gemini-3-flash"


def test_gitlab_uses_official_mcp_endpoint():
    assert GITLAB_MCP_URL == "https://gitlab.com/api/v4/mcp"


def test_adk_mcp_filter_blocks_mutations():
    assert _read_only_mcp_tool(_Tool("get_issue"))
    assert _read_only_mcp_tool(_Tool("list_merge_requests"))
    assert not _read_only_mcp_tool(_Tool("create_issue"))
    assert not _read_only_mcp_tool(_Tool("gitlab_create_issue"))
    assert not _read_only_mcp_tool(_Tool("merge_merge_request"))
