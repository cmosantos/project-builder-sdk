from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from project_builder.orchestration.state import (
    ExecutionEvent,
    ProjectState,
)


def format_duration(
    elapsed_ms: float,
) -> str:
    if elapsed_ms < 1000:
        return f"{elapsed_ms:.0f} ms"

    return f"{elapsed_ms / 1000:.2f} s"


def format_event_time(
    event: ExecutionEvent,
) -> str:
    return event.occurred_at.astimezone().strftime(
        "%H:%M:%S"
    )


def format_event_flow(
    event: ExecutionEvent,
) -> str:
    if event.event_type in {
        "stage_transition",
        "handoff",
    }:
        if event.source and event.target:
            return f"{event.source} -> {event.target}"

    if event.event_type == "agent_activated":
        if event.target:
            return event.target

    if event.event_type == "agent_cleared":
        if event.source:
            return f"{event.source} -> idle"

    if event.event_type == "repair_attempt":
        attempt = event.details.get(
            "attempt",
            "?",
        )
        origin = event.details.get(
            "origin",
            event.source or "?",
        )

        return (
            f"repair #{attempt} "
            f"origin={origin}"
        )

    if event.event_type == "failure":
        error = event.details.get(
            "error",
            "",
        )

        if error:
            return str(error)

        return "workflow failed"

    if event.source and event.target:
        return f"{event.source} -> {event.target}"

    if event.target:
        return event.target

    if event.source:
        return event.source

    return "-"


def build_execution_timeline(
    state: ProjectState,
) -> Panel:
    table = Table(
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )

    table.add_column(
        "#",
        justify="right",
        width=3,
        no_wrap=True,
    )
    table.add_column(
        "Time",
        no_wrap=True,
        width=8,
    )
    table.add_column(
        "Δ",
        justify="right",
        no_wrap=True,
        width=9,
    )
    table.add_column(
        "Stage",
        style="cyan",
        no_wrap=True,
    )
    table.add_column(
        "Event",
        style="magenta",
        no_wrap=True,
    )
    table.add_column(
        "Flow",
        overflow="fold",
    )

    if not state.execution_events:
        table.add_row(
            "-",
            "-",
            "-",
            state.stage.value,
            "no_events",
            "Nenhum evento registrado.",
        )

    for event in state.execution_events:
        table.add_row(
            str(event.sequence),
            format_event_time(event),
            format_duration(event.elapsed_ms),
            event.stage,
            event.event_type,
            format_event_flow(event),
        )

    total_elapsed_ms = sum(
        event.elapsed_ms
        for event in state.execution_events
    )

    subtitle = (
        f"{len(state.execution_events)} eventos"
        f" · {format_duration(total_elapsed_ms)}"
    )

    if state.build_id:
        subtitle += (
            f" · Build {state.build_id}"
        )

    return Panel(
        table,
        title=Text(
            "EXECUTION TIMELINE",
            style="bold cyan",
        ),
        subtitle=subtitle,
        border_style="cyan",
        padding=(1, 1),
    )


def render_execution_timeline(
    console: Console,
    state: ProjectState,
) -> None:
    console.print()
    console.print(
        build_execution_timeline(state)
    )