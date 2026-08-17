from dataclasses import asdict, dataclass
from typing import Literal

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from project_builder.orchestration.runtime_quality import (
    build_runtime_quality_snapshot,
    runtime_recovered,
)
from project_builder.orchestration.state import (
    ProjectStage,
    ProjectState,
)


HealthLevel = Literal[
    "PASS",
    "WARN",
    "FAIL",
]


EXPECTED_HANDOFFS = (
    "Project Router -> Project Architect",
    "Project Architect -> Project Developer",
)


@dataclass(frozen=True)
class BuildHealthFinding:
    code: str
    level: HealthLevel
    message: str


def _finding(
    code: str,
    level: HealthLevel,
    message: str,
) -> BuildHealthFinding:
    return BuildHealthFinding(
        code=code,
        level=level,
        message=message,
    )


def evaluate_build_health(
    state: ProjectState,
    *,
    sandbox_cleanup_ok: bool | None = None,
) -> list[BuildHealthFinding]:
    findings: list[BuildHealthFinding] = []

    if state.stage == ProjectStage.COMPLETED:
        findings.append(
            _finding(
                "workflow_completed",
                "PASS",
                "Workflow completed successfully.",
            )
        )
    elif state.stage == ProjectStage.FAILED:
        findings.append(
            _finding(
                "workflow_failed",
                "FAIL",
                "Workflow finished in FAILED state.",
            )
        )
    else:
        findings.append(
            _finding(
                "workflow_incomplete",
                "WARN",
                (
                    "Workflow finished at stage "
                    f"{state.stage.value}."
                ),
            )
        )

    qa_report = getattr(
        state.context,
        "qa_report",
        None,
    )

    if qa_report is None:
        findings.append(
            _finding(
                "qa_not_executed",
                "WARN",
                "QA was not executed.",
            )
        )
    elif getattr(
        qa_report,
        "status",
        None,
    ) == "APROVADO":
        findings.append(
            _finding(
                "qa_approved",
                "PASS",
                (
                    "QA approved"
                    f" · {getattr(qa_report, 'score', '?')}/100."
                ),
            )
        )
    else:
        findings.append(
            _finding(
                "qa_failed",
                "FAIL",
                (
                    "QA did not approve the build"
                    f" · {getattr(qa_report, 'score', '?')}/100."
                ),
            )
        )

    runtime_report = getattr(
        state.context,
        "runtime_report",
        None,
    )

    if runtime_report is None:
        findings.append(
            _finding(
                "runtime_not_executed",
                "WARN",
                "Runtime gate was not executed.",
            )
        )
    elif getattr(
        runtime_report,
        "status",
        None,
    ) == "APROVADO":
        runtime_quality = build_runtime_quality_snapshot(
            runtime_report
        )

        warning_count = int(
            runtime_quality[
                "warning_count"
            ]
        )

        warning_detected = bool(
            runtime_quality[
                "warning_detected"
            ]
        )

        if warning_count > 0:
            warning_message = (
                "Runtime gate approved, but pytest emitted "
                f"{warning_count} warning(s)."
            )
        elif warning_detected:
            warning_message = (
                "Runtime gate approved, but pytest warning(s) "
                "were detected without a numeric count."
            )
        else:
            warning_message = ""

        if warning_detected:
            findings.append(
                _finding(
                    "runtime_warnings",
                    "WARN",
                    warning_message,
                )
            )
        else:
            findings.append(
                _finding(
                    "runtime_healthy",
                    "PASS",
                    "Runtime gate approved without pytest warnings.",
                )
            )
    else:
        findings.append(
            _finding(
                "runtime_failed",
                "FAIL",
                "Runtime gate did not approve the build.",
            )
        )

    if runtime_recovered(
        state
    ):
        history = state.runtime_history

        flow = " -> ".join(
            (
                f"#{attempt['attempt']} "
                f"{attempt['quality_status']}"
            )
            for attempt in history
        )

        findings.append(
            _finding(
                "runtime_recovered",
                "PASS",
                (
                    "Runtime recovered after a previous failure"
                    f" · {flow}."
                ),
            )
        )

    if state.repair_attempts == 0:
        findings.append(
            _finding(
                "no_repairs",
                "PASS",
                "No repair attempts were required.",
            )
        )
    else:
        findings.append(
            _finding(
                "repairs_required",
                "WARN",
                (
                    f"{state.repair_attempts} repair attempt(s)"
                    " were required."
                ),
            )
        )

    missing_handoffs = [
        handoff
        for handoff in EXPECTED_HANDOFFS
        if handoff not in state.handoff_history
    ]

    if not missing_handoffs:
        findings.append(
            _finding(
                "handoffs_complete",
                "PASS",
                (
                    "Required agent handoffs completed"
                    f" · {len(EXPECTED_HANDOFFS)}/{len(EXPECTED_HANDOFFS)}."
                ),
            )
        )
    else:
        findings.append(
            _finding(
                "handoffs_missing",
                (
                    "FAIL"
                    if state.stage
                    in {
                        ProjectStage.COMPLETED,
                        ProjectStage.FAILED,
                    }
                    else "WARN"
                ),
                (
                    "Missing required handoff(s): "
                    + ", ".join(
                        missing_handoffs
                    )
                    + "."
                ),
            )
        )

    if sandbox_cleanup_ok is True:
        findings.append(
            _finding(
                "sandbox_cleanup_ok",
                "PASS",
                "Sandbox cleanup completed.",
            )
        )
    elif sandbox_cleanup_ok is False:
        findings.append(
            _finding(
                "sandbox_cleanup_pending",
                "FAIL",
                "Sandbox cleanup is pending.",
            )
        )

    return findings


def build_health_snapshot(
    state: ProjectState,
    *,
    sandbox_cleanup_ok: bool | None = None,
) -> dict[str, object]:
    findings = evaluate_build_health(
        state,
        sandbox_cleanup_ok=sandbox_cleanup_ok,
    )

    pass_count = sum(
        finding.level == "PASS"
        for finding in findings
    )

    warn_count = sum(
        finding.level == "WARN"
        for finding in findings
    )

    fail_count = sum(
        finding.level == "FAIL"
        for finding in findings
    )

    if fail_count > 0:
        status = "UNHEALTHY"
    elif warn_count > 0:
        status = "ATTENTION"
    else:
        status = "HEALTHY"

    return {
        "status": status,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "findings": [
            asdict(
                finding
            )
            for finding in findings
        ],
    }


def format_health_summary(
    state: ProjectState,
    *,
    sandbox_cleanup_ok: bool | None = None,
) -> str:
    snapshot = build_health_snapshot(
        state,
        sandbox_cleanup_ok=sandbox_cleanup_ok,
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

    return (
        f"{status_markup}"
        f" · {snapshot['pass_count']} PASS"
        f" · {snapshot['warn_count']} WARN"
        f" · {snapshot['fail_count']} FAIL"
    )


def _level_markup(
    level: str,
) -> str:
    if level == "PASS":
        return "[green]✓ PASS[/green]"

    if level == "WARN":
        return "[yellow]⚠ WARN[/yellow]"

    return "[red]✗ FAIL[/red]"


def build_health_panel(
    state: ProjectState,
    *,
    sandbox_cleanup_ok: bool | None = None,
) -> Panel:
    snapshot = build_health_snapshot(
        state,
        sandbox_cleanup_ok=sandbox_cleanup_ok,
    )

    table = Table(
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )

    table.add_column(
        "Health",
        width=9,
        no_wrap=True,
    )

    table.add_column(
        "Check",
        style="cyan",
        no_wrap=True,
    )

    table.add_column(
        "Insight",
        overflow="fold",
    )

    for finding in snapshot[
        "findings"
    ]:
        table.add_row(
            _level_markup(
                str(
                    finding[
                        "level"
                    ]
                )
            ),
            str(
                finding[
                    "code"
                ]
            ),
            str(
                finding[
                    "message"
                ]
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
    else:
        border_style = "red"

    subtitle = (
        f"{snapshot['pass_count']} PASS"
        f" · {snapshot['warn_count']} WARN"
        f" · {snapshot['fail_count']} FAIL"
    )

    return Panel(
        table,
        title=Text(
            f"BUILD HEALTH · {status}",
            style=f"bold {border_style}",
        ),
        subtitle=subtitle,
        border_style=border_style,
        padding=(1, 1),
    )


def render_build_health(
    console: Console,
    state: ProjectState,
    *,
    sandbox_cleanup_ok: bool | None = None,
) -> None:
    console.print()
    console.print(
        build_health_panel(
            state,
            sandbox_cleanup_ok=sandbox_cleanup_ok,
        )
    )