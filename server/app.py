import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .agent_ws import WebSocketAgent

app = FastAPI(title="vixcode")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def load_config() -> dict:
    for p in [
        Path.cwd() / "vixcode.json",
        Path(__file__).parent.parent / "config.json",
    ]:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()

    config = load_config()
    ollama_url = config.get("ollama_url", os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    model = config.get("model", os.environ.get("VIXCODE_MODEL", "qwen2.5-coder"))

    agent = WebSocketAgent(llm_url=ollama_url, model=model, ws=websocket)
    agent_task: asyncio.Task | None = None

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            t = data.get("type")

            if t == "get_info":
                await websocket.send_json({"type": "info", "model": model, "ollama": ollama_url})

            elif t == "user_message":
                # Don't start a new run while one is in progress
                if agent_task and not agent_task.done():
                    await websocket.send_json({"type": "error", "message": "Agent is busy. Wait or /reset."})
                    continue
                agent_task = asyncio.create_task(agent.run(data["content"]))

            elif t == "permission_response":
                await agent.handle_permission(data.get("approved", False))

            elif t == "reset":
                if agent_task and not agent_task.done():
                    agent_task.cancel()
                agent.reset()
                await websocket.send_json({"type": "reset_done"})

    except WebSocketDisconnect:
        if agent_task and not agent_task.done():
            agent_task.cancel()
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
