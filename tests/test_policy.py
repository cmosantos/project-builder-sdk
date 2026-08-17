from types import SimpleNamespace

from rich.console import Console

from project_builder.orchestration.policy import (
    BuildPolicy,
    build_policy_panel,
    build_policy_snapshot,
    evaluate_build_policy,
    format_policy_summary,
)
from project_builder.orchestration.state import (
    AgentUsageMetric,
    ExecutionEvent,
    ProjectState,
)


def make_state() -> ProjectState:
    state = ProjectState(
        request="Criar API FastAPI"
    )

    state.context = SimpleNamespace(
        qa_report=SimpleNamespace(
            status="APROVADO",
            score=98,
        ),
        runtime_report=SimpleNamespace(
            status="APROVADO",
            http_check=SimpleNamespace(
                comando="http live",
                sucesso=True,
            ),
        ),
    )

    state.handoff_history.extend(
        [
            "Project Router -> Project Architect",
            "Project Architect -> Project Developer",
        ]
    )

    state.execution_events.extend(
        [
            ExecutionEvent(
                sequence=1,
                event_type="stage_transition",
                stage="routing",
                elapsed_ms=20_000.0,
            ),
            ExecutionEvent(
                sequence=2,
                event_type="stage_transition",
                stage="completed",
                elapsed_ms=30_000.0,
            ),
        ]
    )

    state.agent_usage.append(
        AgentUsageMetric(
            sequence=1,
            agent_name="Project Developer",
            stage="development",
            requests=2,
            input_tokens=8_000,
            output_tokens=2_000,
            total_tokens=10_000,
        )
    )

    return state


def check_by_code(
    checks,
    code: str,
):
    return next(
        check
        for check in checks
        if check.code == code
    )


def test_default_policy_passes_clean_build():
    state = make_state()

    snapshot = build_policy_snapshot(
        state,
        sandbox_cleanup_ok=True,
    )

    assert snapshot[
        "status"
    ] == "PASS"

    assert snapshot[
        "pass_count"
    ] == 8

    assert snapshot[
        "violation_count"
    ] == 0


def test_qa_approval_violation():
    state = make_state()
    state.context.qa_report.status = "REPROVADO"

    checks = evaluate_build_policy(
        state,
        sandbox_cleanup_ok=True,
    )

    assert check_by_code(
        checks,
        "qa_approval",
    ).level == "VIOLATION"


def test_runtime_and_http_violations():
    state = make_state()
    state.context.runtime_report.status = "REPROVADO"
    state.context.runtime_report.http_check.sucesso = False

    checks = evaluate_build_policy(
        state,
        sandbox_cleanup_ok=True,
    )

    assert check_by_code(
        checks,
        "runtime_pass",
    ).level == "VIOLATION"

    assert check_by_code(
        checks,
        "http_live",
    ).level == "VIOLATION"


def test_sandbox_cleanup_violation():
    state = make_state()

    checks = evaluate_build_policy(
        state,
        sandbox_cleanup_ok=False,
    )

    assert check_by_code(
        checks,
        "sandbox_cleanup",
    ).level == "VIOLATION"


def test_required_handoff_violation():
    state = make_state()

    state.handoff_history.remove(
        "Project Architect -> Project Developer"
    )

    checks = evaluate_build_policy(
        state,
        sandbox_cleanup_ok=True,
    )

    assert check_by_code(
        checks,
        "required_handoffs",
    ).level == "VIOLATION"


def test_repair_budget_violation():
    state = make_state()
    state.repair_attempts = 3

    policy = BuildPolicy(
        max_repairs=2,
    )

    checks = evaluate_build_policy(
        state,
        policy=policy,
        sandbox_cleanup_ok=True,
    )

    assert check_by_code(
        checks,
        "repair_budget",
    ).level == "VIOLATION"


def test_duration_budget_violation():
    state = make_state()

    policy = BuildPolicy(
        max_duration_seconds=40.0,
    )

    checks = evaluate_build_policy(
        state,
        policy=policy,
        sandbox_cleanup_ok=True,
    )

    assert check_by_code(
        checks,
        "duration_budget",
    ).level == "VIOLATION"


def test_token_budget_violation():
    state = make_state()

    policy = BuildPolicy(
        max_total_tokens=5_000,
    )

    checks = evaluate_build_policy(
        state,
        policy=policy,
        sandbox_cleanup_ok=True,
    )

    assert check_by_code(
        checks,
        "token_budget",
    ).level == "VIOLATION"


def test_summary_and_panel_render():
    state = make_state()

    summary = format_policy_summary(
        state,
        sandbox_cleanup_ok=True,
    )

    assert "PASS" in summary
    assert "8 PASS" in summary
    assert "0 VIOLATIONS" in summary

    panel = build_policy_panel(
        state,
        sandbox_cleanup_ok=True,
    )

    console = Console(
        record=True,
        width=160,
    )

    console.print(
        panel
    )

    output = console.export_text()

    assert "BUILD POLICY · PASS" in output
    assert "qa_approval" in output
    assert "duration_budget" in output
    assert "token_budget" in output