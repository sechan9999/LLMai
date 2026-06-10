"""Regression tests for privacy boundaries."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from llmai.memory.store import MemoryStore
from llmai.telemetry import _preview_args
from llmai.tools import _references_path_outside_workspace, _safe_subprocess_env
from server import app as server_app


def test_shell_blocks_absolute_path_outside_workspace():
    assert _references_path_outside_workspace("cat /etc/passwd") == "/etc/passwd"


def test_shell_blocks_relative_parent_traversal():
    assert _references_path_outside_workspace("cat ../secrets.txt") == "../secrets.txt"


def test_shell_subprocess_does_not_inherit_unrelated_secrets(monkeypatch):
    monkeypatch.setenv("SUPER_SECRET_API_KEY", "do-not-leak")
    assert "SUPER_SECRET_API_KEY" not in _safe_subprocess_env()


def test_telemetry_redacts_sensitive_values():
    preview = _preview_args({
        "command": "curl https://example.test/?token=secret",
        "path": "src/app.py",
    })
    assert "secret" not in preview
    assert "curl" not in preview
    assert "src/app.py" not in preview
    assert "path=<redacted:10 chars>" in preview


def test_memory_stores_metadata_only_by_default():
    store = MemoryStore(uri="mongodb://unused", db_name="test")
    messages = [
        {"role": "user", "content": "my password is hunter2"},
        {
            "role": "assistant",
            "content": "reading",
            "tool_calls": [{"function": {"name": "read_file", "arguments": "{}"}}],
        },
    ]

    stored = store._messages_for_storage(messages)

    assert "hunter2" not in repr(stored)
    assert stored[0] == {"role": "user", "content_chars": 22}
    assert stored[1]["tool_calls"] == ["read_file"]


def test_memory_full_transcripts_require_explicit_opt_in():
    store = MemoryStore(
        uri="mongodb://unused",
        db_name="test",
        store_transcripts=True,
    )
    messages = [{"role": "user", "content": "private"}]
    assert store._messages_for_storage(messages) is messages


def test_memory_transcript_env_overrides_config(monkeypatch):
    monkeypatch.setenv("LLMAI_MEMORY_ENABLED", "true")
    monkeypatch.setenv("LLMAI_MEMORY_URI", "mongodb://unused")
    monkeypatch.setenv("LLMAI_MEMORY_STORE_TRANSCRIPTS", "false")
    store = MemoryStore.from_config({"store_transcripts": True})
    assert store is not None
    assert store.store_transcripts is False


def test_websocket_origin_defaults_to_localhost_only():
    assert server_app._origin_allowed(
        "http://localhost:7777",
        "localhost:7777",
    )
    assert not server_app._origin_allowed(
        "https://attacker.example",
        "attacker.example",
    )


def test_websocket_token_uses_constant_time_check():
    good = SimpleNamespace(query_params={"token": server_app._WS_TOKEN})
    bad = SimpleNamespace(query_params={"token": "wrong"})
    assert server_app._ws_token_allowed(good)
    assert not server_app._ws_token_allowed(bad)


def test_websocket_accepts_authenticated_local_browser():
    client = TestClient(server_app.app, base_url="http://localhost:7777")
    token = client.get("/session").json()["ws_token"]
    with client.websocket_connect(
        f"/ws?token={token}",
        headers={
            "origin": "http://localhost:7777",
            "host": "localhost:7777",
        },
    ) as ws:
        ws.send_json({"type": "get_info"})
        assert ws.receive_json()["type"] == "info"


def test_websocket_rejects_cross_origin_browser():
    client = TestClient(server_app.app, base_url="http://localhost:7777")
    token = client.get("/session").json()["ws_token"]
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/ws?token={token}",
            headers={"origin": "https://attacker.example"},
        ):
            pass


def test_frontend_sanitizes_markdown_and_uses_ephemeral_storage():
    html = (server_app.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert "let rendered = esc(text)" in html
    assert "marked.parse" not in html
    assert "fonts.googleapis.com" not in html
    assert "cdn.jsdelivr.net" not in html
    assert "sessionStorage.getItem" in html
    assert "localStorage.getItem" not in html
