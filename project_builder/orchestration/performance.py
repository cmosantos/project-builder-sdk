from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from project_builder.orchestration.state import (
    ProjectState,
)
from project_builder.orchestration.usage import (
    aggregate_agent_usage,
    usage_totals,
)


def _format_duration(
    elapsed_ms: float,
) -> str:
    if elapsed_ms < 1000:
        return f"{elapsed_ms:.0f} ms"

    return f"{elapsed_ms / 1000:.2f} s"


def _format_tokens(
    value: int,
) -> str:
    return f"{value:,}".replace(
        ",",
        ".",
    )


def _format_percentage(
    value: float,
) -> str:
    return f"{value:.1f}%"


def calculate_agent_durations(
    state: ProjectState,
) -> dict[str, float]:
    durations: dict[str, float] = {}
    active_agent: str | None = None

    for event in state.execution_events:
        if active_agent is not None:
            durations[active_agent] = (
                durations.get(
                    active_agent,
                    0.0,
                )
                + event.elapsed_ms
            )

        if (
            event.event_type
            == "agent_activated"
            and event.target
        ):
            active_agent = event.target

        elif event.event_type == "agent_cleared":
            active_agent = None

    return durations


def build_agent_performance_rows(
    state: ProjectState,
) -> list[dict[str, object]]:
    durations = calculate_agent_durations(
        state
    )

    usage = aggregate_agent_usage(
        state
    )

    usage_by_agent = {
        str(item["agent_name"]): item
        for item in usage
    }

    order: list[str] = []

    for event in state.execution_events:
        if (
            event.event_type
            == "agent_activated"
            and event.target
            and event.target not in order
        ):
            order.append(
                event.target
            )

    for item in usage:
        agent_name = str(
            item["agent_name"]
        )

        if agent_name not in order:
            order.append(
                agent_name
            )

    total_duration_ms = sum(
        event.elapsed_ms
        for event in state.execution_events
    )

    totals = usage_totals(
        state
    )

    total_tokens = totals[
        "total_tokens"
    ]

    rows: list[dict[str, object]] = []

    for agent_name in order:
        item = usage_by_agent.get(
            agent_name,
            {},
        )

        duration_ms = durations.get(
            agent_name,
            0.0,
        )

        tokens = int(
            item.get(
                "total_tokens",
                0,
            )
        )

        requests = int(
            item.get(
                "requests",
                0,
            )
        )

        time_share = (
            duration_ms
            / total_duration_ms
            * 100.0
            if total_duration_ms > 0
            else 0.0
        )

        token_share = (
            tokens
            / total_tokens
            * 100.0
            if total_tokens > 0
            else 0.0
        )

        rows.append(
            {
                "agent_name": agent_name,
                "duration_ms": round(
                    duration_ms,
                    2,
                ),
                "time_share": time_share,
                "requests": requests,
                "total_tokens": tokens,
                "token_share": token_share,
            }
        )

    return rows


def build_performance_snapshot(
    state: ProjectState,
) -> dict[str, object]:
    rows = build_agent_performance_rows(
        state
    )

    total_duration_ms = sum(
        event.elapsed_ms
        for event in state.execution_events
    )

    agent_duration_ms = sum(
        float(
            row["duration_ms"]
        )
        for row in rows
    )

    non_agent_duration_ms = max(
        total_duration_ms
        - agent_duration_ms,
        0.0,
    )

    totals = usage_totals(
        state
    )

    slowest = max(
        rows,
        key=lambda row: float(
            row["duration_ms"]
        ),
        default=None,
    )

    highest_usage = max(
        rows,
        key=lambda row: int(
            row["total_tokens"]
        ),
        default=None,
    )

    most_requests = max(
        rows,
        key=lambda row: int(
            row["requests"]
        ),
        default=None,
    )

    qa_report = state.context.qa_report
    runtime_report = state.context.runtime_report

    return {
        "total_duration_ms": round(
            total_duration_ms,
            2,
        ),
        "agent_duration_ms": round(
            agent_duration_ms,
            2,
        ),
        "non_agent_duration_ms": round(
            non_agent_duration_ms,
            2,
        ),
        "total_requests": totals[
            "requests"
        ],
        "total_tokens": totals[
            "total_tokens"
        ],
        "slowest_agent": (
            slowest["agent_name"]
            if slowest is not None
            else None
        ),
        "slowest_agent_ms": (
            slowest["duration_ms"]
            if slowest is not None
            else 0.0
        ),
        "slowest_agent_share": (
            slowest["time_share"]
            if slowest is not None
            else 0.0
        ),
        "highest_usage_agent": (
            highest_usage["agent_name"]
            if highest_usage is not None
            else None
        ),
        "highest_usage_tokens": (
            highest_usage["total_tokens"]
            if highest_usage is not None
            else 0
        ),
        "highest_usage_share": (
            highest_usage["token_share"]
            if highest_usage is not None
            else 0.0
        ),
        "most_requests_agent": (
            most_requests["agent_name"]
            if most_requests is not None
            else None
        ),
        "most_requests": (
            most_requests["requests"]
            if most_requests is not None
            else 0
        ),
        "qa_status": (
            qa_report.status
            if qa_report is not None
            else None
        ),
        "qa_score": (
            qa_report.score
            if qa_report is not None
            else None
        ),
        "runtime_status": (
            runtime_report.status
            if runtime_report is not None
            else None
        ),
        "repair_attempts": (
            state.repair_attempts
        ),
        "agents": rows,
    }


def format_performance_summary(
    state: ProjectState,
) -> str:
    snapshot = build_performance_snapshot(
        state
    )

    slowest = snapshot[
        "slowest_agent"
    ]

    highest_usage = snapshot[
        "highest_usage_agent"
    ]

    if slowest is None:
        return (
            "[dim]"
            "Performance ainda não disponível."
            "[/dim]"
        )

    return (
        f"Slowest "
        f"[bold]{slowest}[/bold] · "
        f"{_format_duration(float(snapshot['slowest_agent_ms']))}"
        f"  |  Usage "
        f"[bold]{highest_usage or '-'}[/bold] · "
        f"{_format_tokens(int(snapshot['highest_usage_tokens']))} tokens"
    )


def build_performance_panel(
    state: ProjectState,
) -> Panel:
    snapshot = build_performance_snapshot(
        state
    )

    summary = Table.grid(
        padding=(0, 2)
    )

    summary.add_column(
        style="bold cyan",
        no_wrap=True,
    )
    summary.add_column()

    summary.add_row(
        "Total build",
        _format_duration(
            float(
                snapshot[
                    "total_duration_ms"
                ]
            )
        ),
    )

    summary.add_row(
        "Agent time",
        _format_duration(
            float(
                snapshot[
                    "agent_duration_ms"
                ]
            )
        ),
    )

    summary.add_row(
        "System / Runtime",
        _format_duration(
            float(
                snapshot[
                    "non_agent_duration_ms"
                ]
            )
        ),
    )

    slowest_agent = snapshot[
        "slowest_agent"
    ]

    if slowest_agent is not None:
        summary.add_row(
            "Slowest agent",
            (
                f"[bold]{slowest_agent}[/bold]"
                f" · {_format_duration(float(snapshot['slowest_agent_ms']))}"
                f" · {_format_percentage(float(snapshot['slowest_agent_share']))}"
            ),
        )

    highest_usage_agent = snapshot[
        "highest_usage_agent"
    ]

    if highest_usage_agent is not None:
        summary.add_row(
            "Highest usage",
            (
                f"[bold]{highest_usage_agent}[/bold]"
                f" · {_format_tokens(int(snapshot['highest_usage_tokens']))} tokens"
                f" · {_format_percentage(float(snapshot['highest_usage_share']))}"
            ),
        )

    most_requests_agent = snapshot[
        "most_requests_agent"
    ]

    if most_requests_agent is not None:
        summary.add_row(
            "Most requests",
            (
                f"[bold]{most_requests_agent}[/bold]"
                f" · {int(snapshot['most_requests'])}"
            ),
        )

    if snapshot["qa_score"] is not None:
        summary.add_row(
            "QA",
            (
                f"{snapshot['qa_status']}"
                f" · {snapshot['qa_score']}/100"
            ),
        )

    summary.add_row(
        "Repairs",
        str(
            snapshot[
                "repair_attempts"
            ]
        ),
    )

    agents = Table(
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )

    agents.add_column(
        "Agent",
        style="cyan",
        no_wrap=True,
    )

    agents.add_column(
        "Time",
        justify="right",
        no_wrap=True,
    )

    agents.add_column(
        "Build %",
        justify="right",
        no_wrap=True,
    )

    agents.add_column(
        "Req",
        justify="right",
        no_wrap=True,
    )

    agents.add_column(
        "Tokens",
        justify="right",
        no_wrap=True,
    )

    agents.add_column(
        "LLM %",
        justify="right",
        no_wrap=True,
    )

    rows = snapshot[
        "agents"
    ]

    if not rows:
        agents.add_row(
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
        )

    for row in rows:
        agents.add_row(
            str(
                row["agent_name"]
            ),
            _format_duration(
                float(
                    row[
                        "duration_ms"
                    ]
                )
            ),
            _format_percentage(
                float(
                    row[
                        "time_share"
                    ]
                )
            ),
            str(
                row[
                    "requests"
                ]
            ),
            _format_tokens(
                int(
                    row[
                        "total_tokens"
                    ]
                )
            ),
            _format_percentage(
                float(
                    row[
                        "token_share"
                    ]
                )
            ),
        )

    body = Group(
        summary,
        Text(""),
        agents,
    )

    return Panel(
        body,
        title=Text(
            "BUILD PERFORMANCE",
            style="bold cyan",
        ),
        subtitle=(
            f"{int(snapshot['total_requests'])} requests"
            f" · {_format_tokens(int(snapshot['total_tokens']))} tokens"
        ),
        border_style="cyan",
        padding=(1, 1),
    )


def render_performance_summary(
    console: Console,
    state: ProjectState,
) -> None:
    console.print()
    console.print(
        build_performance_panel(
            state
        )
    )