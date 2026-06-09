"""
FastAPI application for the llmai Web UI.

Serves the single-page frontend and manages WebSocket connections
for the agentic chat loop.
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from llmai import elastic, memory, telemetry
from llmai import tools as _vt
from llmai._logging import configure_logging
from llmai.llm import resolve_provider_config

from .agent_ws import WebSocketAgent

configure_logging()

logger = logging.getLogger(__name__)

app = FastAPI(title="llmai", description="Local AI Coding Agent")


@app.on_event("startup")
async def _init_observability() -> None:
    """Initialize OTel + memory + Elastic once when the server boots."""
    cfg = load_config()
    telemetry.init(cfg.get("telemetry"))
    memory.init(cfg.get("memory"))
    elastic.init(cfg.get("elastic"))
    _vt.register_memory_tool()
    _vt.register_elastic_tools()


STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Valid WebSocket message types ─────────────────────────────────────────────
_VALID_TYPES = {"get_info", "user_message", "permission_response", "reset", "cancel"}


def load_config() -> dict:
    """Load configuration from the first available config file."""
    for p in [
        Path.cwd() / "llmai.json",
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


@app.get("/healthz")
async def healthz():
    """Liveness probe — returns 200 with optional-layer status."""
    return {
        "status": "ok",
        "service": "llmai",
        "version": _detect_version(),
        "workspace": str(_vt.WORKSPACE_ROOT),
        "layers": {
            "telemetry": telemetry.is_active(),
            "memory":    memory.is_enabled(),
            "elastic":   elastic.is_enabled(),
        },
    }


# ── Briefing routes ───────────────────────────────────────────────────────────

_briefing_lock = asyncio.Lock()
_briefing_generating = False

BRIEFING_PATH = STATIC_DIR / "daily_briefing_dashboard.html"


@app.get("/briefing")
async def get_briefing():
    """Serve the daily briefing dashboard.

    Returns the pre-generated HTML if it exists; otherwise triggers
    generation and returns a loading page.
    """
    if BRIEFING_PATH.exists():
        return FileResponse(str(BRIEFING_PATH), media_type="text/html")
    # No briefing yet — return a lightweight loading page
    return HTMLResponse(_loading_page(), status_code=200)


@app.post("/briefing/refresh")
async def refresh_briefing(background_tasks: BackgroundTasks):
    """Trigger async regeneration of the daily briefing.

    Returns immediately; the new HTML is written to static/ in the background.
    Poll GET /briefing/status to check progress.
    """
    global _briefing_generating
    if _briefing_generating:
        return JSONResponse({"status": "already_running"})
    background_tasks.add_task(_generate_briefing)
    return JSONResponse({"status": "started"})


@app.get("/briefing/status")
async def briefing_status():
    """Check whether a briefing exists and whether generation is running."""
    return JSONResponse({
        "exists": BRIEFING_PATH.exists(),
        "generating": _briefing_generating,
        "last_modified": (
            datetime.fromtimestamp(BRIEFING_PATH.stat().st_mtime).isoformat()
            if BRIEFING_PATH.exists() else None
        ),
    })


async def _generate_briefing() -> None:
    """Generate a fresh daily briefing HTML and write it to static/.

    Steps:
      1. Pick today's DS interview topic (deterministic by day-of-month mod 8).
      2. Call local Ollama to generate the question + model answer.
      3. Fetch Korea news headlines via RSS.
      4. Fetch US market summary via Yahoo Finance RSS.
      5. Assemble and write the HTML dashboard.
    """
    global _briefing_generating
    async with _briefing_lock:
        _briefing_generating = True
        try:
            cfg = load_config()
            ollama_url = os.environ.get("OLLAMA_URL") or cfg.get("ollama_url", "http://localhost:11434")
            model      = os.environ.get("LLMAI_MODEL") or cfg.get("model", "qwen2.5-coder")

            today      = datetime.now()
            date_str   = today.strftime("%A, %B %d, %Y")
            day_mod    = today.day % 8

            topics = [
                "Statistics & Probability",
                "Machine Learning Fundamentals",
                "Deep Learning & Neural Networks",
                "Feature Engineering & Data Preprocessing",
                "Model Evaluation & Metrics",
                "SQL & Data Manipulation",
                "ML System Design",
                "Python / Pandas / NumPy Coding",
            ]
            topic = topics[day_mod]

            # ── Step 1: Generate DS interview Q&A via Ollama ──────────────────
            ds_html = await _llm_ds_question(ollama_url, model, topic)

            # ── Step 2: Fetch Korea news (KBS World RSS) ──────────────────────
            korea_html = await _fetch_korea_news()

            # ── Step 3: Fetch US market summary (Yahoo Finance RSS) ───────────
            market_html = await _fetch_market_news()

            # ── Step 4: Assemble dashboard HTML ───────────────────────────────
            html = _build_briefing_html(date_str, topic, ds_html, korea_html, market_html)
            BRIEFING_PATH.write_text(html, encoding="utf-8")
            logger.info("Briefing generated successfully → %s", BRIEFING_PATH)

        except Exception:
            logger.exception("Failed to generate briefing")
        finally:
            _briefing_generating = False


async def _llm_ds_question(ollama_url: str, model: str, topic: str) -> str:
    """Call Ollama to generate a DS interview question for the given topic."""
    prompt = (
        f"Generate a single mid-to-senior level data science interview question on the topic: '{topic}'.\n\n"
        "Format your response as HTML using only these tags: "
        "<p>, <ul>, <li>, <strong>, <pre><code>.\n\n"
        "Include:\n"
        "1. The question text (in a <p> with class 'question-text')\n"
        "2. A model answer as a <ul> with 4-6 <li> bullet points\n"
        "3. A code snippet in <pre><code> if relevant\n"
        "4. A follow-up question in a <p> with class 'followup'\n\n"
        "Keep the total response under 600 words. Return only HTML, no markdown."
    )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{ollama_url}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            return content
    except Exception as e:
        logger.warning("LLM call failed: %s", e)
        return f"<p class='question-text'>Could not generate question: {e}</p>"


async def _fetch_korea_news() -> str:
    """Fetch top Korea headlines from KBS World RSS and return HTML list items."""
    feeds = [
        "https://world.kbs.co.kr/rss/rss_news.htm?lang=e",
        "https://koreajoongangdaily.joins.com/rss/news.xml",
    ]
    items: list[dict] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in feeds:
            try:
                r = await client.get(url, follow_redirects=True)
                if r.status_code == 200:
                    items += _parse_rss(r.text, limit=3)
                    if len(items) >= 5:
                        break
            except Exception as e:
                logger.debug("Korea RSS fetch failed (%s): %s", url, e)

    if not items:
        return "<p style='color:var(--muted)'>Could not fetch Korea news. Check your internet connection.</p>"

    html_parts = []
    for i, item in enumerate(items[:5], 1):
        html_parts.append(
            f'<div class="news-item">'
            f'<div class="news-num">{i}</div>'
            f'<div class="news-body">'
            f'<div class="news-headline">{_esc(item["title"])}</div>'
            f'<div class="news-summary">{_esc(item["desc"])}</div>'
            f'<div class="news-source">{_esc(item["source"])}</div>'
            f'</div></div>'
        )
    return "\n".join(html_parts)


async def _fetch_market_news() -> str:
    """Fetch US market headlines from Yahoo Finance RSS and return HTML."""
    url = "https://finance.yahoo.com/news/rssindex"
    items: list[dict] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(url, follow_redirects=True)
            if r.status_code == 200:
                items = _parse_rss(r.text, limit=4)
        except Exception as e:
            logger.debug("Market RSS fetch failed: %s", e)

    if not items:
        return "<p style='color:var(--muted)'>Could not fetch market news.</p>"

    html_parts = []
    for item in items:
        html_parts.append(
            f'<div class="mover-row" style="flex-direction:column;align-items:flex-start;gap:4px;margin-bottom:10px">'
            f'<div class="news-headline" style="font-size:13px;font-weight:600">{_esc(item["title"])}</div>'
            f'<div class="news-source">{_esc(item["source"])}</div>'
            f'</div>'
        )
    return "\n".join(html_parts)


def _parse_rss(xml: str, limit: int = 5) -> list[dict]:
    """Very lightweight RSS parser — no external deps."""
    import re
    items = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)[:limit]:
        title = _tag(block, "title")
        desc  = _tag(block, "description") or _tag(block, "summary") or ""
        desc  = re.sub(r"<[^>]+>", "", desc)[:160].strip()
        items.append({"title": title or "—", "desc": desc, "source": "RSS"})
    return items


def _tag(text: str, name: str) -> str:
    import re
    m = re.search(rf"<{name}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{name}>", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _loading_page() -> str:
    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  body{background:#0f1117;color:#8890a8;font-family:system-ui,sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}
  .box{text-align:center;gap:12px;display:flex;flex-direction:column;align-items:center;}
  .spinner{width:32px;height:32px;border:3px solid #2e3350;
           border-top-color:#5b8dee;border-radius:50%;animation:spin .8s linear infinite;}
  @keyframes spin{to{transform:rotate(360deg)}}
  button{background:#22263a;border:1px solid #2e3350;color:#5b8dee;
         border-radius:8px;padding:8px 18px;cursor:pointer;font-size:13px;}
</style></head>
<body><div class="box">
  <div class="spinner"></div>
  <div>Generating today's briefing…</div>
  <button onclick="location.reload()">Reload</button>
</div></body></html>"""


def _build_briefing_html(date_str: str, topic: str, ds_html: str, korea_html: str, market_html: str) -> str:
    """Assemble the full briefing dashboard HTML."""
    # Read the template from static if it exists, otherwise use the embedded template
    template_path = STATIC_DIR / "briefing_template.html"
    if template_path.exists():
        template = template_path.read_text(encoding="utf-8")
        return (template
                .replace("{{DATE}}", date_str)
                .replace("{{TOPIC}}", topic)
                .replace("{{DS_HTML}}", ds_html)
                .replace("{{KOREA_HTML}}", korea_html)
                .replace("{{MARKET_HTML}}", market_html))

    # Inline fallback template
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Daily Briefing — {date_str}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1"
  integrity="sha384-jb8JQMbMoBUzgWatfe6COACi2ljcDdZQ2OxczGA3bGNeWe+6DChMTBJemed7ZnvJ"
  crossorigin="anonymous"></script>
<style>
:root{{--bg:#0f1117;--surface:#1a1d27;--surface2:#22263a;--border:#2e3350;
      --accent:#5b8dee;--accent2:#f0c040;--accent3:#4ecb71;--red:#f05555;
      --text:#e4e8f0;--muted:#8890a8;--radius:12px;--gap:18px;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:var(--bg);color:var(--text);min-height:100vh;padding:24px;}}
.header{{display:flex;align-items:center;justify-content:space-between;
         margin-bottom:28px;flex-wrap:wrap;gap:12px;}}
.header h1{{font-size:22px;font-weight:700;}}
.date-badge{{background:var(--surface2);border:1px solid var(--border);
            border-radius:20px;padding:6px 16px;font-size:13px;color:var(--muted);}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:var(--gap);margin-bottom:var(--gap);}}
.card{{background:var(--surface);border:1px solid var(--border);
      border-radius:var(--radius);padding:22px 24px;}}
.section-title{{font-size:15px;font-weight:700;margin-bottom:16px;
               display:flex;align-items:center;gap:8px;}}
.topic-badge{{display:inline-block;background:rgba(91,141,238,.15);
             border:1px solid rgba(91,141,238,.35);color:var(--accent);
             border-radius:20px;padding:4px 14px;font-size:12px;
             font-weight:600;margin-bottom:14px;}}
.question-text{{font-size:15px;font-weight:600;line-height:1.6;margin-bottom:14px;}}
.followup{{margin-top:14px;background:rgba(240,192,64,.07);
          border:1px solid rgba(240,192,64,.25);border-radius:8px;
          padding:12px 16px;font-size:13px;color:var(--accent2);}}
ul{{padding-left:20px;}} li{{margin-bottom:8px;font-size:14px;line-height:1.65;color:#c8d0e0;}}
pre{{background:#0d1117;border:1px solid var(--border);border-radius:8px;
    padding:14px;font-size:12px;overflow-x:auto;margin-top:12px;color:#a8d8a8;}}
.news-list{{display:flex;flex-direction:column;gap:14px;}}
.news-item{{display:flex;gap:14px;padding-bottom:14px;border-bottom:1px solid var(--border);}}
.news-item:last-child{{border-bottom:none;padding-bottom:0;}}
.news-num{{flex-shrink:0;width:26px;height:26px;background:rgba(91,141,238,.15);
          border-radius:50%;display:flex;align-items:center;justify-content:center;
          font-size:12px;font-weight:700;color:var(--accent);}}
.news-body{{flex:1;}}
.news-headline{{font-size:14px;font-weight:600;margin-bottom:5px;line-height:1.4;}}
.news-summary{{font-size:13px;color:#a0a8c0;line-height:1.55;margin-bottom:4px;}}
.news-source{{font-size:11px;color:var(--muted);font-weight:600;}}
.refresh-btn{{float:right;background:var(--surface2);border:1px solid var(--border);
             color:var(--accent);border-radius:8px;padding:6px 14px;
             font-size:12px;font-weight:600;cursor:pointer;}}
.refresh-btn:hover{{background:rgba(91,141,238,.1);}}
@media(max-width:700px){{.grid-2{{grid-template-columns:1fr;}}}}
</style></head>
<body><div style="max-width:1200px;margin:0 auto;">
<div class="header">
  <div>
    <h1>☀️ Daily Morning Briefing</h1>
    <div style="font-size:13px;color:var(--muted);margin-top:3px;">
      Data Science Practice · Korea News · US Markets
    </div>
  </div>
  <div style="display:flex;gap:10px;align-items:center;">
    <div class="date-badge">{date_str}</div>
    <button class="refresh-btn" onclick="refreshBriefing()">↻ Refresh</button>
  </div>
</div>

<div class="grid-2">
  <div class="card">
    <div class="section-title"><span>🧠</span> DS Interview Practice</div>
    <div class="topic-badge">Topic: {topic}</div>
    {ds_html}
  </div>
  <div class="card">
    <div class="section-title"><span>📈</span> US Market News</div>
    {market_html}
  </div>
</div>

<div class="card">
  <div class="section-title"><span>🇰🇷</span> Korea Morning News</div>
  <div class="news-list">{korea_html}</div>
</div>

<div style="text-align:center;margin-top:24px;font-size:12px;color:var(--muted);">
  LLMai Daily Briefing · Generated {date_str}
</div>
</div>
<script>
async function refreshBriefing() {{
  const btn = document.querySelector('.refresh-btn');
  btn.textContent = '⏳ Generating…'; btn.disabled = true;
  await fetch('http://localhost:7777/briefing/refresh', {{method:'POST'}});
  setTimeout(() => location.reload(), 15000);
}}
</script>
</body></html>"""


def _detect_version() -> str:
    try:
        from importlib.metadata import version
        return version("llmai-agent")
    except Exception:
        return "unknown"


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    """WebSocket endpoint for the agent chat loop."""
    await websocket.accept()

    config = load_config()
    cfg_url   = os.environ.get("OLLAMA_URL")    or config.get("ollama_url")
    cfg_model = os.environ.get("LLMAI_MODEL") or config.get("model")
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
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON message"})
                continue

            t = data.get("type")
            if t not in _VALID_TYPES:
                await websocket.send_json({"type": "error", "message": f"Unknown message type: {t}"})
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
                    await websocket.send_json({"type": "error", "message": "Empty message"})
                    continue
                if agent_task and not agent_task.done():
                    await websocket.send_json({"type": "error", "message": "Agent is busy. Wait or reset."})
                    continue
                agent_task = asyncio.create_task(agent.run(content))
            elif t == "permission_response":
                await agent.handle_permission(data.get("approved", False))
            elif t == "cancel":
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
