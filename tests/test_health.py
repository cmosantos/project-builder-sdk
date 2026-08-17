from types import SimpleNamespace

from rich.console import Console

from project_builder.orchestration.health import (
    build_health_panel,
    build_health_snapshot,
    evaluate_build_health,
    format_health_summary,
)
from project_builder.orchestration.state import (
    AgentUsageMetric,
    ExecutionEvent,
    ProjectStage,
    ProjectState,
)


def make_runtime_report(
    *,
    warnings: int = 0,
):
    warning_text = (
        f"{warnings} warnings"
        if warnings > 0
        else ""
    )

    return SimpleNamespace(
        status="APROVADO",
        smoke_test=SimpleNamespace(
            sucesso=True,
            comando="python smoke",
            stdout="",
            stderr="",
        ),
        pytest=SimpleNamespace(
            sucesso=True,
            comando="pytest",
            stdout=(
                "11 passed"
                + (
                    f", {warning_text}"
                    if warning_text
                    else ""
                )
                + " in 0.38s"
            ),
            stderr="",
        ),
        http_check=SimpleNamespace(
            sucesso=True,
            comando="http",
            stdout="",
            stderr="",
        ),
    )


def make_completed_state(
    *,
    runtime_warnings: int = 0,
) -> ProjectState:
    state = ProjectState(
        request="Criar API FastAPI"
    )

    state.stage = ProjectStage.COMPLETED

    state.context = SimpleNamespace(
        qa_report=SimpleNamespace(
            status="APROVADO",
            score=97,
        ),
        runtime_report=make_runtime_report(
            warnings=runtime_warnings,
        ),
    )

    state.handoff_history.extend(
        [
            "Project Router -> Project Architect",
            "Project Architect -> Project Developer",
        ]
    )

    return state


def add_heavy_developer_performance(
    state: ProjectState,
) -> None:
    state.execution_events.extend(
        [
            ExecutionEvent(
                sequence=1,
                event_type="agent_activated",
                stage="routing",
                target="Project Developer",
                elapsed_ms=1.0,
            ),
            ExecutionEvent(
                sequence=2,
                event_type="agent_cleared",
                stage="qa",
                source="Project Developer",
                elapsed_ms=900.0,
            ),
            ExecutionEvent(
                sequence=3,
                event_type="stage_transition",
                stage="completed",
                source="runtime",
                target="completed",
                elapsed_ms=100.0,
            ),
        ]
    )

    state.agent_usage.extend(
        [
            AgentUsageMetric(
                sequence=1,
                agent_name="Project Developer",
                stage="development",
                requests=2,
                input_tokens=8_000,
                output_tokens=2_000,
                total_tokens=10_000,
            ),
            AgentUsageMetric(
                sequence=2,
                agent_name="Project QA",
                stage="qa",
                requests=1,
                input_tokens=500,
                output_tokens=500,
                total_tokens=1_000,
            ),
        ]
    )


def finding_by_code(
    findings,
    code: str,
):
    return next(
        finding
        for finding in findings
        if finding.code == code
    )


def finding_codes(
    findings,
) -> set[str]:
    return {
        finding.code
        for finding in findings
    }


def test_completed_clean_build_has_core_passes():
    state = make_completed_state()

    findings = evaluate_build_health(
        state,
        sandbox_cleanup_ok=True,
    )

    assert finding_by_code(
        findings,
        "workflow_completed",
    ).level == "PASS"

    assert finding_by_code(
        findings,
        "qa_approved",
    ).level == "PASS"

    assert finding_by_code(
        findings,
        "runtime_healthy",
    ).level == "PASS"

    assert finding_by_code(
        findings,
        "no_repairs",
    ).level == "PASS"

    assert finding_by_code(
        findings,
        "handoffs_complete",
    ).level == "PASS"

    assert finding_by_code(
        findings,
        "sandbox_cleanup_ok",
    ).level == "PASS"


def test_clean_build_snapshot_is_healthy():
    state = make_completed_state()

    snapshot = build_health_snapshot(
        state,
        sandbox_cleanup_ok=True,
    )

    assert snapshot[
        "status"
    ] == "HEALTHY"

    assert snapshot[
        "pass_count"
    ] == 6

    assert snapshot[
        "warn_count"
    ] == 0

    assert snapshot[
        "fail_count"
    ] == 0


def test_performance_concentration_does_not_affect_health():
    state = make_completed_state()

    add_heavy_developer_performance(
        state
    )

    findings = evaluate_build_health(
        state,
        sandbox_cleanup_ok=True,
    )

    codes = finding_codes(
        findings
    )

    assert "time_hotspot" not in codes
    assert "time_distribution_ok" not in codes
    assert "token_hotspot" not in codes
    assert "token_distribution_ok" not in codes

    snapshot = build_health_snapshot(
        state,
        sandbox_cleanup_ok=True,
    )

    assert snapshot[
        "status"
    ] == "HEALTHY"


def test_runtime_warnings_generate_attention():
    state = make_completed_state(
        runtime_warnings=5,
    )

    snapshot = build_health_snapshot(
        state,
        sandbox_cleanup_ok=True,
    )

    assert snapshot[
        "status"
    ] == "ATTENTION"

    assert finding_by_code(
        evaluate_build_health(
            state,
            sandbox_cleanup_ok=True,
        ),
        "runtime_warnings",
    ).level == "WARN"


def test_repairs_generate_warning():
    state = make_completed_state()
    state.repair_attempts = 1

    findings = evaluate_build_health(
        state,
        sandbox_cleanup_ok=True,
    )

    repair = finding_by_code(
        findings,
        "repairs_required",
    )

    assert repair.level == "WARN"


def test_missing_handoff_is_failure_after_completion():
    state = make_completed_state()

    state.handoff_history.remove(
        "Project Architect -> Project Developer"
    )

    findings = evaluate_build_health(
        state,
        sandbox_cleanup_ok=True,
    )

    handoff = finding_by_code(
        findings,
        "handoffs_missing",
    )

    assert handoff.level == "FAIL"


def test_sandbox_cleanup_pending_is_failure():
    state = make_completed_state()

    findings = evaluate_build_health(
        state,
        sandbox_cleanup_ok=False,
    )

    cleanup = finding_by_code(
        findings,
        "sandbox_cleanup_pending",
    )

    assert cleanup.level == "FAIL"


def test_summary_and_panel_render_healthy_build():
    state = make_completed_state()

    summary = format_health_summary(
        state,
        sandbox_cleanup_ok=True,
    )

    assert "HEALTHY" in summary
    assert "6 PASS" in summary
    assert "0 WARN" in summary
    assert "0 FAIL" in summary

    panel = build_health_panel(
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

    assert "BUILD HEALTH · HEALTHY" in output
    assert "runtime_healthy" in output
    assert "time_hotspot" not in output
    assert "token_hotspot" not in output