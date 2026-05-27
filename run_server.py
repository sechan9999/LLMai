"""
Entry point: python run_server.py
"""
import json
import os
import sys
import webbrowser
from pathlib import Path


def main():
    port = int(os.environ.get("PORT", "7777"))
    # 0.0.0.0 when running in Docker; 127.0.0.1 otherwise
    host = os.environ.get("HOST", "127.0.0.1")
    url  = f"http://localhost:{port}"

    # Print config summary
    config_path = Path(__file__).parent / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())
    model = config.get("model", os.environ.get("LLMAI_MODEL", "qwen2.5-coder"))
    ollama = config.get("ollama_url", "http://localhost:11434")

    print(f"""
  +--------------------------------------+
  |  llmai -- Local AI Coding Agent    |
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

    # Open browser only when running locally (not in container)
    if host == "127.0.0.1":
        import threading
        import time
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
