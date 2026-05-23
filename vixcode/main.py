"""
vixcode — Local AI Coding Agent
Usage: python -m vixcode  (or `vixcode` after pip install)
"""
import os
import sys
import json
from pathlib import Path

try:
    import readline  # noqa: F401  (adds arrow-key history on Unix/macOS)
except ImportError:
    pass  # Windows without pyreadline — still works, just no history

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from . import telemetry
from .llm import OllamaClient, make_default_client, resolve_provider_config
from .permissions import PermissionManager
from .agent import AgentLoop

console = Console()


# ── Config loading ────────────────────────────────────────────────────────────

def load_config() -> dict:
    for p in [
        Path.cwd() / "vixcode.json",
        Path.home() / ".vixcode" / "config.json",
        Path(__file__).parent.parent / "config.json",
    ]:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


# ── REPL ──────────────────────────────────────────────────────────────────────

def main():
    config = load_config()
    telemetry.init(config.get("telemetry"))
    # Config-file overrides; otherwise fall through to environment-driven
    # provider selection (Gemini if GEMINI_API_KEY is set, else Ollama).
    cfg_base_url = config.get("ollama_url")
    cfg_model    = config.get("model")
    llm = make_default_client(base_url=cfg_base_url, model=cfg_model)

    permissions = PermissionManager()
    agent       = AgentLoop(llm=llm, permissions=permissions)

    provider_label = {
        "ollama": "Ollama (local)",
        "gemini": "Google Gemini",
        "custom": "Custom OpenAI-compat",
    }.get(llm.provider, llm.provider)

    # ── Startup banner ────────────────────────────────────────────────────────
    console.print(Panel(
        f"[bold cyan]vixcode[/bold cyan]  —  AI Coding Agent\n"
        f"  Provider: [magenta]{provider_label}[/magenta]\n"
        f"  Model   : [yellow]{llm.model}[/yellow]\n"
        f"  URL     : [green]{llm.base_url}[/green]\n\n"
        f"[dim]Commands: /reset  /model <name>  /models  /perms  /tokens  /exit[/dim]",
        border_style="cyan",
        padding=(0, 1),
    ))

    # ── Health check (Ollama only — cloud providers can't be probed) ──────────
    if not llm.is_available():
        console.print(f"[red]✗ Ollama not reachable at {llm.base_url}[/red]")
        console.print("[yellow]  → Run: ollama serve[/yellow]")
        sys.exit(1)

    if llm.provider == "ollama":
        available = llm.list_models()
        if available and not any(m.startswith(llm.model.split(":")[0]) for m in available):
            console.print(f"[yellow]⚠  Model '{llm.model}' not found locally.[/yellow]")
            console.print(f"[yellow]   Available: {', '.join(available[:5])}[/yellow]")
            console.print(f"[yellow]   Pull it: ollama pull {llm.model}[/yellow]")

    # ── Main REPL loop ────────────────────────────────────────────────────────
    while True:
        try:
            user_input = input("\n\033[96m[vixcode]\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Bye.[/dim]")
            break

        if not user_input:
            continue

        # Built-in commands
        if user_input in ("/exit", "/quit", "exit", "quit"):
            console.print("[dim]Bye.[/dim]")
            break

        if user_input == "/reset":
            agent.reset()
            console.print("[green]✓ Context cleared.[/green]")
            continue

        if user_input.startswith("/model "):
            new_model = user_input[7:].strip()
            llm.model = new_model
            console.print(f"[green]✓ Model → {new_model}[/green]")
            continue

        if user_input == "/models":
            models = llm.list_models()
            console.print("  " + "  ".join(models) if models else "  (none found)")
            continue

        if user_input == "/tokens":
            console.print(f"  Estimated tokens in context: ~{agent.token_estimate}")
            continue

        if user_input == "/perms":
            for tool, mode in permissions.rules.items():
                color = {"allow": "green", "ask": "yellow", "deny": "red"}.get(mode, "white")
                console.print(f"  {tool:<15} [{color}]{mode}[/{color}]")
            continue

        if user_input == "/compress":
            agent.maybe_compress(threshold=0)
            console.print("[green]✓ Context compressed.[/green]")
            continue

        # Agent turn
        console.print(Rule(style="dim"))
        try:
            agent.maybe_compress()
            agent.run(user_input)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    main()
