"""
FastAPI application for the vixcode Web UI.

Serves the single-page frontend and manages WebSocket connections
for the agentic chat loop.
"""
import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from vixcode import telemetry
from vixcode.llm import resolve_provider_config
from vixcode import tools as _vt

from .agent_ws import WebSocketAgent

logger = logging.getLogger(__name__)

app = FastAPI(title="vixcode", description="Local AI Coding Agent")


@app.on_event("startup")
async def _init_telemetry() -> None:
    """Initialize OpenTelemetry once when the server boots."""
    cfg = load_config()
    telemetry.init(cfg.get("telemetry"))


STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Valid WebSocket message types ─────────────────────────────────────────────
_VALID_TYPES = {"get_info", "user_message", "permission_response", "reset", "cancel"}


def load_config() -> dict:
    """Load configuration from the first available config file."""
    for p in [
        Path.cwd() / "vixcode.json",
        Path(__file__).parent.parent / "config.json",
    ]:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Failed to load config from %s: %s", p, e)
    return {}


@app.get("/")
async def index():
    """Serve the main Web UI page."""
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    """WebSocket endpoint for the agent chat loop.

    Handles message routing between the browser client and the
    async agent loop, including permission request/response flow.
    """
    await websocket.accept()

    config = load_config()
    cfg_url   = os.environ.get("OLLAMA_URL")    or config.get("ollama_url")
    cfg_model = os.environ.get("VIXCODE_MODEL") or config.get("model")
    # Auto-detect provider — Gemini if GEMINI_API_KEY is set, else Ollama.
    provider_cfg = resolve_provider_config(base_url=cfg_url, model=cfg_model)

    agent = WebSocketAgent(
        llm_url=provider_cfg["base_url"],
        model=provider_cfg["model"],
        ws=websocket,
        chat_path=provider_cfg["chat_path"],
        headers=provider_cfg["headers"],
        provider=provider_cfg["provider"],
    )
    agent_task: asyncio.Task | None = None

    try:
        while True:
            raw = await websocket.receive_text()

            # P1: Validate incoming JSON
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON message",
                })
                continue

            t = data.get("type")

            if t not in _VALID_TYPES:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {t}",
                })
                continue

            if t == "get_info":
                await websocket.send_json({
                    "type": "info",
                    "model": provider_cfg["model"],
                    "ollama": provider_cfg["base_url"],
                    "provider": provider_cfg["provider"],
                    "workspace": str(_vt.WORKSPACE_ROOT),
                })

            elif t == "user_message":
                content = data.get("content", "").strip()
                if not content:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Empty message",
                    })
                    continue
                # Don't start a new run while one is in progress
                if agent_task and not agent_task.done():
                    await websocket.send_json({
                        "type": "error",
                        "message": "Agent is busy. Wait or reset.",
                    })
                    continue
                agent_task = asyncio.create_task(agent.run(content))

            elif t == "permission_response":
                await agent.handle_permission(data.get("approved", False))

            elif t == "cancel":
                # Stop the in-flight agent run without wiping conversation history.
                if agent_task and not agent_task.done():
                    agent_task.cancel()
                    try:
                        await agent_task
                    except (asyncio.CancelledError, Exception):
                        pass
                    await websocket.send_json({"type": "cancelled"})
                await websocket.send_json({"type": "done"})

            elif t == "reset":
                if agent_task and not agent_task.done():
                    agent_task.cancel()
                    try:
                        await agent_task
                    except (asyncio.CancelledError, Exception):
                        pass
                agent.reset()
                await websocket.send_json({"type": "reset_done"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        if agent_task and not agent_task.done():
            agent_task.cancel()
    except Exception as e:
        logger.exception("WebSocket error")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
