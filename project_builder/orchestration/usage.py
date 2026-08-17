from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from project_builder.orchestration.state import (
    ProjectState,
)


def _format_tokens(
    value: int,
) -> str:
    return f"{value:,}".replace(
        ",",
        ".",
    )


def aggregate_agent_usage(
    state: ProjectState,
) -> list[dict[str, int | str]]:
    aggregated: dict[
        str,
        dict[str, int | str],
    ] = {}

    order: list[str] = []

    for metric in state.agent_usage:
        agent_name = metric.agent_name

        if agent_name not in aggregated:
            aggregated[agent_name] = {
                "agent_name": agent_name,
                "runs": 0,
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cached_tokens": 0,
                "reasoning_tokens": 0,
            }

            order.append(
                agent_name
            )

        item = aggregated[
            agent_name
        ]

        item["runs"] = int(
            item["runs"]
        ) + 1

        item["requests"] = int(
            item["requests"]
        ) + metric.requests

        item["input_tokens"] = int(
            item["input_tokens"]
        ) + metric.input_tokens

        item["output_tokens"] = int(
            item["output_tokens"]
        ) + metric.output_tokens

        item["total_tokens"] = int(
            item["total_tokens"]
        ) + metric.total_tokens

        item["cached_tokens"] = int(
            item["cached_tokens"]
        ) + metric.cached_tokens

        item["reasoning_tokens"] = int(
            item["reasoning_tokens"]
        ) + metric.reasoning_tokens

    return [
        aggregated[agent_name]
        for agent_name in order
    ]


def usage_totals(
    state: ProjectState,
) -> dict[str, int]:
    return {
        "runs": len(
            state.agent_usage
        ),
        "requests": sum(
            metric.requests
            for metric in state.agent_usage
        ),
        "input_tokens": sum(
            metric.input_tokens
            for metric in state.agent_usage
        ),
        "output_tokens": sum(
            metric.output_tokens
            for metric in state.agent_usage
        ),
        "total_tokens": sum(
            metric.total_tokens
            for metric in state.agent_usage
        ),
        "cached_tokens": sum(
            metric.cached_tokens
            for metric in state.agent_usage
        ),
        "reasoning_tokens": sum(
            metric.reasoning_tokens
            for metric in state.agent_usage
        ),
    }


def format_usage_summary(
    state: ProjectState,
) -> str:
    totals = usage_totals(
        state
    )

    if not state.agent_usage:
        return (
            "[dim]"
            "Uso do modelo não registrado."
            "[/dim]"
        )

    return (
        f"{totals['requests']} req · "
        f"{_format_tokens(totals['input_tokens'])} in · "
        f"{_format_tokens(totals['output_tokens'])} out · "
        f"[bold]{_format_tokens(totals['total_tokens'])} total[/bold]"
    )


def build_agent_usage_panel(
    state: ProjectState,
) -> Panel:
    table = Table(
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )

    table.add_column(
        "Agent",
        style="cyan",
        no_wrap=True,
    )
    table.add_column(
        "Runs",
        justify="right",
        no_wrap=True,
    )
    table.add_column(
        "Req",
        justify="right",
        no_wrap=True,
    )
    table.add_column(
        "Input",
        justify="right",
        no_wrap=True,
    )
    table.add_column(
        "Output",
        justify="right",
        no_wrap=True,
    )
    table.add_column(
        "Total",
        justify="right",
        style="bold",
        no_wrap=True,
    )
    table.add_column(
        "Cached",
        justify="right",
        no_wrap=True,
    )
    table.add_column(
        "Reasoning",
        justify="right",
        no_wrap=True,
    )

    aggregated = aggregate_agent_usage(
        state
    )

    if not aggregated:
        table.add_row(
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
        )

    for item in aggregated:
        table.add_row(
            str(item["agent_name"]),
            str(item["runs"]),
            str(item["requests"]),
            _format_tokens(
                int(item["input_tokens"])
            ),
            _format_tokens(
                int(item["output_tokens"])
            ),
            _format_tokens(
                int(item["total_tokens"])
            ),
            _format_tokens(
                int(item["cached_tokens"])
            ),
            _format_tokens(
                int(item["reasoning_tokens"])
            ),
        )

    totals = usage_totals(
        state
    )

    subtitle = (
        f"{len(aggregated)} agentes · "
        f"{totals['requests']} requests · "
        f"{_format_tokens(totals['total_tokens'])} tokens"
    )

    return Panel(
        table,
        title=Text(
            "AGENT USAGE",
            style="bold cyan",
        ),
        subtitle=subtitle,
        border_style="cyan",
        padding=(1, 1),
    )


def render_agent_usage(
    console: Console,
    state: ProjectState,
) -> None:
    console.print()
    console.print(
        build_agent_usage_panel(
            state
        )
    )
