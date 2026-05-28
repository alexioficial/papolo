import sys
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .agent import Agent


def main():
    console = Console()
    console.print(Panel.fit("[bold cyan]Papolo[/bold cyan]  —  escribe 'salir' para terminar", border_style="cyan"))

    agent = Agent()

    def on_event(kind, data):
        if kind == "tool_call":
            console.print(f"[dim]→ {data['name']}({list(data['args'].keys())})[/dim]")

    while True:
        try:
            user_input = console.input("\n[bold green]>[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]chau[/dim]")
            return
        if user_input.lower() in {"salir", "exit", "quit"}:
            return
        if not user_input:
            continue
        try:
            result = agent.send(user_input, on_event=on_event)
        except Exception as e:
            console.print(f"[red]ERROR: {e}[/red]")
            continue
        console.print(Markdown(result))


if __name__ == "__main__":
    main()
