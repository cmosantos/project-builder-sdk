from dataclasses import asdict, dataclass
from typing import Literal

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from project_builder.orchestration.performance import (
    build_performance_snapshot,
)
from project_builder.orchestration.state import (
    ProjectState,
)
from project_builder.orchestration.usage import (
    usage_totals,
)


PolicyLevel = Literal[
    "PASS",
    "VIOLATION",
]


EXPECTED_HANDOFFS = (
    "Project Router -> Project Architect",
    "Project Architect -> Project Developer",
)


@dataclass(frozen=True)
class BuildPolicy:
    require_qa_approval: bool = True
    require_runtime_pass: bool = True
    require_http_pass: bool = True
    require_sandbox_cleanup: bool = True
    require_handoffs: bool = True

    max_repairs: int = 2
    max_duration_seconds: float = 120.0
    max_total_tokens: int = 50_000


DEFAULT_BUILD_POLICY = BuildPolicy()


@dataclass(frozen=True)
class BuildPolicyCheck:
    code: str
    level: PolicyLevel
    message: str


def _check(
    code: str,
    passed: bool,
    message: str,
) -> BuildPolicyCheck:
    return BuildPolicyCheck(
        code=code,
        level=(
            "PASS"
            if passed
            else "VIOLATION"
        ),
        message=message,
    )


def evaluate_build_policy(
    state: ProjectState,
    *,
    policy: BuildPolicy = DEFAULT_BUILD_POLICY,
    sandbox_cleanup_ok: bool | None = None,
) -> list[BuildPolicyCheck]:
    checks: list[BuildPolicyCheck] = []

    qa_report = getattr(
        state.context,
        "qa_report",
        None,
    )

    qa_approved = (
        qa_report is not None
        and getattr(
            qa_report,
            "status",
            None,
        ) == "APROVADO"
    )

    if policy.require_qa_approval:
        checks.append(
            _check(
                "qa_approval",
                qa_approved,
                (
                    "QA approval required"
                    + (
                        " · satisfied."
                        if qa_approved
                        else " · not satisfied."
                    )
                ),
            )
        )

    runtime_report = getattr(
        state.context,
        "runtime_report",
        None,
    )

    runtime_passed = (
        runtime_report is not None
        and getattr(
            runtime_report,
            "status",
            None,
        ) == "APROVADO"
    )

    if policy.require_runtime_pass:
        checks.append(
            _check(
                "runtime_pass",
                runtime_passed,
                (
                    "Runtime approval required"
                    + (
                        " · satisfied."
                        if runtime_passed
                        else " · not satisfied."
                    )
                ),
            )
        )

    http_check = (
        getattr(
            runtime_report,
            "http_check",
            None,
        )
        if runtime_report is not None
        else None
    )

    http_passed = (
        http_check is not None
        and bool(
            getattr(
                http_check,
                "comando",
                None,
            )
        )
        and bool(
            getattr(
                http_check,
                "sucesso",
                False,
            )
        )
    )

    if policy.require_http_pass:
        checks.append(
            _check(
                "http_live",
                http_passed,
                (
                    "HTTP Live Check required"
                    + (
                        " · PASS."
                        if http_passed
                        else " · not satisfied."
                    )
                ),
            )
        )

    if policy.require_sandbox_cleanup:
        cleanup_passed = (
            sandbox_cleanup_ok is True
        )

        checks.append(
            _check(
                "sandbox_cleanup",
                cleanup_passed,
                (
                    "Sandbox cleanup required"
                    + (
                        " · completed."
                        if cleanup_passed
                        else " · not confirmed."
                    )
                ),
            )
        )

    if policy.require_handoffs:
        missing_handoffs = [
            handoff
            for handoff in EXPECTED_HANDOFFS
            if handoff
            not in state.handoff_history
        ]

        handoffs_passed = (
            not missing_handoffs
        )

        checks.append(
            _check(
                "required_handoffs",
                handoffs_passed,
                (
                    "Required handoffs"
                    f" · {len(EXPECTED_HANDOFFS) - len(missing_handoffs)}"
                    f"/{len(EXPECTED_HANDOFFS)} completed."
                    if handoffs_passed
                    else (
                        "Required handoffs missing: "
                        + ", ".join(
                            missing_handoffs
                        )
                        + "."
                    )
                ),
            )
        )

    repairs_passed = (
        state.repair_attempts
        <= policy.max_repairs
    )

    checks.append(
        _check(
            "repair_budget",
            repairs_passed,
            (
                f"Repairs {state.repair_attempts}"
                f"/{policy.max_repairs}."
            ),
        )
    )

    performance = build_performance_snapshot(
        state
    )

    duration_seconds = (
        float(
            performance[
                "total_duration_ms"
            ]
        )
        / 1000.0
    )

    duration_passed = (
        duration_seconds
        <= policy.max_duration_seconds
    )

    checks.append(
        _check(
            "duration_budget",
            duration_passed,
            (
                f"Duration {duration_seconds:.2f}s"
                f" / {policy.max_duration_seconds:.0f}s."
            ),
        )
    )

    totals = usage_totals(
        state
    )

    total_tokens = int(
        totals[
            "total_tokens"
        ]
    )

    token_passed = (
        total_tokens
        <= policy.max_total_tokens
    )

    checks.append(
        _check(
            "token_budget",
            token_passed,
            (
                f"Tokens {_format_tokens(total_tokens)}"
                f" / {_format_tokens(policy.max_total_tokens)}."
            ),
        )
    )

    return checks


def build_policy_snapshot(
    state: ProjectState,
    *,
    policy: BuildPolicy = DEFAULT_BUILD_POLICY,
    sandbox_cleanup_ok: bool | None = None,
) -> dict[str, object]:
    checks = evaluate_build_policy(
        state,
        policy=policy,
        sandbox_cleanup_ok=sandbox_cleanup_ok,
    )

    pass_count = sum(
        check.level == "PASS"
        for check in checks
    )

    violation_count = sum(
        check.level == "VIOLATION"
        for check in checks
    )

    return {
        "status": (
            "PASS"
            if violation_count == 0
            else "VIOLATION"
        ),
        "pass_count": pass_count,
        "violation_count": violation_count,
        "policy": asdict(
            policy
        ),
        "checks": [
            asdict(
                check
            )
            for check in checks
        ],
    }


def _format_tokens(
    value: int,
) -> str:
    return f"{value:,}".replace(
        ",",
        ".",
    )


def format_policy_summary(
    state: ProjectState,
    *,
    policy: BuildPolicy = DEFAULT_BUILD_POLICY,
    sandbox_cleanup_ok: bool | None = None,
) -> str:
    snapshot = build_policy_snapshot(
        state,
        policy=policy,
        sandbox_cleanup_ok=sandbox_cleanup_ok,
    )

    status = str(
        snapshot[
            "status"
        ]
    )

    if status == "PASS":
        status_markup = (
            "[bold green]PASS[/bold green]"
        )
    else:
        status_markup = (
            "[bold red]VIOLATION[/bold red]"
        )

    return (
        f"{status_markup}"
        f" · {snapshot['pass_count']} PASS"
        f" · {snapshot['violation_count']} VIOLATIONS"
    )


def _level_markup(
    level: str,
) -> str:
    if level == "PASS":
        return "[green]✓ PASS[/green]"

    return "[red]✗ VIOLATION[/red]"


def build_policy_panel(
    state: ProjectState,
    *,
    policy: BuildPolicy = DEFAULT_BUILD_POLICY,
    sandbox_cleanup_ok: bool | None = None,
) -> Panel:
    snapshot = build_policy_snapshot(
        state,
        policy=policy,
        sandbox_cleanup_ok=sandbox_cleanup_ok,
    )

    table = Table(
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )

    table.add_column(
        "Policy",
        width=13,
        no_wrap=True,
    )

    table.add_column(
        "Check",
        style="cyan",
        no_wrap=True,
    )

    table.add_column(
        "Rule",
        overflow="fold",
    )

    for check in snapshot[
        "checks"
    ]:
        table.add_row(
            _level_markup(
                str(
                    check[
                        "level"
                    ]
                )
            ),
            str(
                check[
                    "code"
                ]
            ),
            str(
                check[
                    "message"
                ]
            ),
        )

    status = str(
        snapshot[
            "status"
        ]
    )

    border_style = (
        "green"
        if status == "PASS"
        else "red"
    )

    subtitle = (
        f"{snapshot['pass_count']} PASS"
        f" · {snapshot['violation_count']} VIOLATIONS"
    )

    return Panel(
        table,
        title=Text(
            f"BUILD POLICY · {status}",
            style=f"bold {border_style}",
        ),
        subtitle=subtitle,
        border_style=border_style,
        padding=(1, 1),
    )


def render_build_policy(
    console: Console,
    state: ProjectState,
    *,
    policy: BuildPolicy = DEFAULT_BUILD_POLICY,
    sandbox_cleanup_ok: bool | None = None,
) -> None:
    console.print()
    console.print(
        build_policy_panel(
            state,
            policy=policy,
            sandbox_cleanup_ok=sandbox_cleanup_ok,
        )
    )