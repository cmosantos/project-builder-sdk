from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from project_builder.workflow import run_project


console = Console()


def main() -> None:
    console.print()

    console.print(
        Panel.fit(
            "[bold cyan]PROJECT BUILDER SDK[/bold cyan]\n"
            "[dim]Descreva o projeto que você quer construir.[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
    )

    console.print()

    pedido = Prompt.ask(
        "[bold cyan]O que você quer construir?[/bold cyan]"
    ).strip()

    if not pedido:
        console.print(
            "[yellow]Nenhum pedido informado.[/yellow]"
        )
        return

    try:
        run_project(pedido)

    except KeyboardInterrupt:
        console.print()
        console.print(
            "[yellow]Execução cancelada pelo usuário.[/yellow]"
        )

    except Exception as erro:
        console.print()
        console.print(
            Panel.fit(
                f"[bold red]ERRO NO WORKFLOW[/bold red]\n\n"
                f"{erro}",
                border_style="red",
                padding=(1, 2),
            )
        )
        raise


if __name__ == "__main__":
    main()