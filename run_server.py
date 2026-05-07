"""
Entry point: python run_server.py
"""
import os
import sys
import json
import webbrowser
from pathlib import Path


def main():
    port = int(os.environ.get("PORT", "7777"))
    host = os.environ.get("HOST", "127.0.0.1")
    url  = f"http://{host}:{port}"

    # Print config summary
    config_path = Path(__file__).parent / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())
    model = config.get("model", os.environ.get("VIXCODE_MODEL", "qwen2.5-coder"))
    ollama = config.get("ollama_url", "http://localhost:11434")

    print(f"""
  +--------------------------------------+
  |  vixcode -- Local AI Coding Agent    |
  +--------------------------------------+
  |  URL   : {url:<28}|
  |  Model : {model:<28}|
  |  Ollama: {ollama:<28}|
  +--------------------------------------+
  Ctrl+C to stop
""")

    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install uvicorn[standard]")
        sys.exit(1)

    # Open browser after a short delay
    import threading, time
    def _open():
        time.sleep(1.2)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(
        "server.app:app",
        host=host,
        port=port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
