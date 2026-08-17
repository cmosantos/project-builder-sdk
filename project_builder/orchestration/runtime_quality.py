import re
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


_RESULT_PATTERN = re.compile(
    r"(?P<count>\d+)\s+"
    r"(?P<kind>"
    r"passed|failed|errors?|warnings?|"
    r"skipped|xfailed|xpassed"
    r")\b",
    re.IGNORECASE,
)

_WARNING_SIGNAL_PATTERN = re.compile(
    r"warnings?\s+summary"
    r"|\b[A-Za-z_]*Warning\b",
    re.IGNORECASE,
)


def parse_pytest_counts(
    output: str,
) -> dict[str, int]:
    counts = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "warnings": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
    }

    for match in _RESULT_PATTERN.finditer(
        output or ""
    ):
        kind = match.group(
            "kind"
        ).lower()

        if kind in {
            "error",
            "errors",
        }:
            key = "errors"
        elif kind in {
            "warning",
            "warnings",
        }:
            key = "warnings"
        else:
            key = kind

        counts[key] = max(
            counts[key],
            int(
                match.group(
                    "count"
                )
            ),
        )

    return counts


def _pytest_output(
    report: Any,
) -> str:
    pytest_result = getattr(
        report,
        "pytest",
        None,
    )

    if pytest_result is None:
        return ""

    stdout = getattr(
        pytest_result,
        "stdout",
        "",
    ) or ""

    stderr = getattr(
        pytest_result,
        "stderr",
        "",
    ) or ""

    return (
        stdout
        + "\n"
        + stderr
    ).strip()


def _status_from_check(
    check: Any,
    *,
    allow_na: bool = False,
) -> str:
    if check is None:
        return (
            "N/A"
            if allow_na
            else "SKIP"
        )

    command = getattr(
        check,
        "comando",
        None,
    )

    if not command:
        return "SKIP"

    return (
        "PASS"
        if bool(
            getattr(
                check,
                "sucesso",
                False,
            )
        )
        else "FAIL"
    )


def build_runtime_quality_snapshot(
    report: Any,
) -> dict[str, object]:
    if report is None:
        return {
            "status": "NOT_RUN",
            "smoke_status": "SKIP",
            "pytest_status": "SKIP",
            "http_status": "N/A",
            "passed_count": 0,
            "failed_count": 0,
            "error_count": 0,
            "warning_count": 0,
            "warning_detected": False,
            "skipped_count": 0,
            "xfailed_count": 0,
            "xpassed_count": 0,
        }

    smoke_result = getattr(
        report,
        "smoke_test",
        None,
    )

    pytest_result = getattr(
        report,
        "pytest",
        None,
    )

    http_result = getattr(
        report,
        "http_check",
        None,
    )

    smoke_status = _status_from_check(
        smoke_result
    )

    pytest_status = _status_from_check(
        pytest_result
    )

    http_status = _status_from_check(
        http_result,
        allow_na=True,
    )

    pytest_output = _pytest_output(
        report
    )

    counts = parse_pytest_counts(
        pytest_output
    )

    warning_detected = (
        counts["warnings"] > 0
        or bool(
            _WARNING_SIGNAL_PATTERN.search(
                pytest_output
            )
        )
    )

    has_failure = any(
        status == "FAIL"
        for status in (
            smoke_status,
            pytest_status,
            http_status,
        )
    )

    if has_failure:
        status = "UNHEALTHY"
    elif warning_detected:
        status = "ATTENTION"
    else:
        status = "HEALTHY"

    return {
        "status": status,
        "smoke_status": smoke_status,
        "pytest_status": pytest_status,
        "http_status": http_status,
        "passed_count": counts[
            "passed"
        ],
        "failed_count": counts[
            "failed"
        ],
        "error_count": counts[
            "errors"
        ],
        "warning_count": counts[
            "warnings"
        ],
        "warning_detected": warning_detected,
        "skipped_count": counts[
            "skipped"
        ],
        "xfailed_count": counts[
            "xfailed"
        ],
        "xpassed_count": counts[
            "xpassed"
        ],
    }


def _status_markup(
    value: str,
) -> str:
    if value == "PASS":
        return "[green]PASS[/green]"

    if value in {
        "SKIP",
        "N/A",
    }:
        return f"[yellow]{value}[/yellow]"

    return "[red]FAIL[/red]"


def format_runtime_quality_summary(
    report: Any,
) -> str:
    snapshot = build_runtime_quality_snapshot(
        report
    )

    if snapshot[
        "status"
    ] == "NOT_RUN":
        return (
            "[dim]"
            "Runtime quality não disponível."
            "[/dim]"
        )

    status = str(
        snapshot[
            "status"
        ]
    )

    if status == "HEALTHY":
        status_markup = (
            "[bold green]HEALTHY[/bold green]"
        )
    elif status == "ATTENTION":
        status_markup = (
            "[bold yellow]ATTENTION[/bold yellow]"
        )
    else:
        status_markup = (
            "[bold red]UNHEALTHY[/bold red]"
        )

    tests = (
        f"{snapshot['passed_count']} passed"
        if int(
            snapshot[
                "passed_count"
            ]
        ) > 0
        else "pytest sem contagem"
    )

    warnings = int(
        snapshot[
            "warning_count"
        ]
    )

    warning_detected = bool(
        snapshot[
            "warning_detected"
        ]
    )

    if warnings:
        tests += (
            f" · {warnings} warnings"
        )
    elif warning_detected:
        tests += " · warnings detected"

    return (
        f"{status_markup}"
        f" · {tests}"
    )


def build_runtime_quality_panel(
    report: Any,
) -> Panel:
    snapshot = build_runtime_quality_snapshot(
        report
    )

    table = Table.grid(
        padding=(0, 2)
    )

    table.add_column(
        style="bold cyan",
        no_wrap=True,
    )

    table.add_column()

    table.add_row(
        "Smoke",
        _status_markup(
            str(
                snapshot[
                    "smoke_status"
                ]
            )
        ),
    )

    table.add_row(
        "Pytest",
        _status_markup(
            str(
                snapshot[
                    "pytest_status"
                ]
            )
        ),
    )

    table.add_row(
        "HTTP Live",
        _status_markup(
            str(
                snapshot[
                    "http_status"
                ]
            )
        ),
    )

    table.add_row(
        "Tests passed",
        str(
            snapshot[
                "passed_count"
            ]
        ),
    )

    warning_count = int(
        snapshot[
            "warning_count"
        ]
    )

    warning_detected = bool(
        snapshot[
            "warning_detected"
        ]
    )

    if warning_count > 0:
        warning_display = (
            "[yellow]"
            f"{warning_count}"
            "[/yellow]"
        )
    elif warning_detected:
        warning_display = (
            "[yellow]DETECTED[/yellow]"
        )
    else:
        warning_display = (
            "[green]0[/green]"
        )

    table.add_row(
        "Warnings",
        warning_display,
    )

    skipped = int(
        snapshot[
            "skipped_count"
        ]
    )

    if skipped:
        table.add_row(
            "Skipped",
            str(
                skipped
            ),
        )

    status = str(
        snapshot[
            "status"
        ]
    )

    if status == "HEALTHY":
        border_style = "green"
    elif status == "ATTENTION":
        border_style = "yellow"
    elif status == "UNHEALTHY":
        border_style = "red"
    else:
        border_style = "dim"

    return Panel(
        table,
        title=Text(
            f"RUNTIME QUALITY · {status}",
            style=f"bold {border_style}",
        ),
        border_style=border_style,
        padding=(1, 2),
    )


def record_runtime_attempt(
    state: Any,
    report: Any,
) -> dict[str, object]:
    snapshot = build_runtime_quality_snapshot(
        report
    )

    attempt = len(
        state.runtime_history
    ) + 1

    record = {
        "attempt": attempt,
        "report_status": getattr(
            report,
            "status",
            None,
        ),
        "quality_status": snapshot[
            "status"
        ],
        "smoke_status": snapshot[
            "smoke_status"
        ],
        "pytest_status": snapshot[
            "pytest_status"
        ],
        "http_status": snapshot[
            "http_status"
        ],
        "passed_count": snapshot[
            "passed_count"
        ],
        "failed_count": snapshot[
            "failed_count"
        ],
        "error_count": snapshot[
            "error_count"
        ],
        "warning_count": snapshot[
            "warning_count"
        ],
        "warning_detected": snapshot[
            "warning_detected"
        ],
        "skipped_count": snapshot[
            "skipped_count"
        ],
    }

    state.runtime_history.append(
        record
    )

    return record


def runtime_recovered(
    state: Any,
) -> bool:
    history = getattr(
        state,
        "runtime_history",
        [],
    )

    if len(history) < 2:
        return False

    previous_failed = any(
        str(
            attempt.get(
                "quality_status",
                "",
            )
        ) == "UNHEALTHY"
        for attempt in history[:-1]
    )

    final_status = str(
        history[-1].get(
            "quality_status",
            "",
        )
    )

    return (
        previous_failed
        and final_status
        in {
            "HEALTHY",
            "ATTENTION",
        }
    )


def format_runtime_history_summary(
    state: Any,
) -> str:
    history = getattr(
        state,
        "runtime_history",
        [],
    )

    if not history:
        return (
            "[dim]"
            "Nenhuma tentativa registrada."
            "[/dim]"
        )

    parts = [
        (
            f"#{attempt['attempt']} "
            f"{attempt['quality_status']}"
        )
        for attempt in history
    ]

    flow = " → ".join(
        parts
    )

    if runtime_recovered(
        state
    ):
        return (
            "[green]RECOVERED[/green]"
            f" · {flow}"
        )

    return flow


def render_runtime_quality(
    console: Console,
    report: Any,
) -> None:
    console.print()
    console.print(
        build_runtime_quality_panel(
            report
        )
    )