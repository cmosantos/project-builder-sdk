from types import SimpleNamespace

from rich.console import Console

from project_builder.orchestration.health import (
    build_health_snapshot,
    evaluate_build_health,
)
from project_builder.orchestration.runtime_quality import (
    build_runtime_quality_panel,
    build_runtime_quality_snapshot,
    format_runtime_history_summary,
    format_runtime_quality_summary,
    parse_pytest_counts,
    record_runtime_attempt,
    runtime_recovered,
)
from project_builder.orchestration.state import (
    ProjectStage,
    ProjectState,
)


def make_check(
    *,
    success: bool,
    command: str = "command",
    stdout: str = "",
    stderr: str = "",
):
    return SimpleNamespace(
        sucesso=success,
        comando=command,
        stdout=stdout,
        stderr=stderr,
    )


def make_runtime(
    *,
    smoke_success: bool = True,
    pytest_success: bool = True,
    http_success: bool = True,
    pytest_output: str = (
        "11 passed in 0.36s"
    ),
):
    return SimpleNamespace(
        status=(
            "APROVADO"
            if (
                smoke_success
                and pytest_success
                and http_success
            )
            else "REPROVADO"
        ),
        smoke_test=make_check(
            success=smoke_success,
        ),
        pytest=make_check(
            success=pytest_success,
            stdout=pytest_output,
        ),
        http_check=make_check(
            success=http_success,
        ),
    )


def make_completed_state(
    runtime_report,
) -> ProjectState:
    state = ProjectState(
        request="Criar API FastAPI"
    )

    state.stage = ProjectStage.COMPLETED

    state.context = SimpleNamespace(
        qa_report=SimpleNamespace(
            status="APROVADO",
            score=98,
        ),
        runtime_report=runtime_report,
    )

    state.handoff_history.extend(
        [
            "Project Router -> Project Architect",
            "Project Architect -> Project Developer",
        ]
    )

    return state


def finding_by_code(
    findings,
    code: str,
):
    return next(
        finding
        for finding in findings
        if finding.code == code
    )


def test_parse_pytest_counts():
    counts = parse_pytest_counts(
        "11 passed, 2 skipped, 5 warnings in 0.36s"
    )

    assert counts[
        "passed"
    ] == 11

    assert counts[
        "skipped"
    ] == 2

    assert counts[
        "warnings"
    ] == 5


def test_runtime_quality_is_healthy_without_warnings():
    snapshot = build_runtime_quality_snapshot(
        make_runtime()
    )

    assert snapshot[
        "status"
    ] == "HEALTHY"

    assert snapshot[
        "passed_count"
    ] == 11

    assert snapshot[
        "warning_count"
    ] == 0


def test_runtime_quality_is_attention_with_warnings():
    snapshot = build_runtime_quality_snapshot(
        make_runtime(
            pytest_output=(
                "11 passed, 5 warnings in 0.36s"
            )
        )
    )

    assert snapshot[
        "status"
    ] == "ATTENTION"

    assert snapshot[
        "warning_count"
    ] == 5


def test_runtime_quality_is_unhealthy_on_pytest_failure():
    snapshot = build_runtime_quality_snapshot(
        make_runtime(
            pytest_success=False,
            pytest_output=(
                "1 failed, 10 passed in 0.36s"
            ),
        )
    )

    assert snapshot[
        "status"
    ] == "UNHEALTHY"

    assert snapshot[
        "failed_count"
    ] == 1


def test_runtime_quality_is_unhealthy_on_http_failure():
    snapshot = build_runtime_quality_snapshot(
        make_runtime(
            http_success=False,
        )
    )

    assert snapshot[
        "status"
    ] == "UNHEALTHY"

    assert snapshot[
        "http_status"
    ] == "FAIL"


def test_runtime_quality_summary_mentions_warning_count():
    summary = format_runtime_quality_summary(
        make_runtime(
            pytest_output=(
                "11 passed, 5 warnings in 0.36s"
            )
        )
    )

    assert "ATTENTION" in summary
    assert "11 passed" in summary
    assert "5 warnings" in summary


def test_runtime_quality_panel_renders():
    panel = build_runtime_quality_panel(
        make_runtime(
            pytest_output=(
                "11 passed, 5 warnings in 0.36s"
            )
        )
    )

    console = Console(
        record=True,
        width=120,
    )

    console.print(
        panel
    )

    output = console.export_text()

    assert "RUNTIME QUALITY" in output
    assert "ATTENTION" in output
    assert "Warnings" in output
    assert "5" in output


def test_health_adds_runtime_warning_finding():
    runtime_report = make_runtime(
        pytest_output=(
            "11 passed, 5 warnings in 0.36s"
        )
    )

    state = make_completed_state(
        runtime_report
    )

    findings = evaluate_build_health(
        state,
        sandbox_cleanup_ok=True,
    )

    finding = finding_by_code(
        findings,
        "runtime_warnings",
    )

    assert finding.level == "WARN"
    assert "5 warning" in finding.message


def test_health_snapshot_is_attention_for_runtime_warnings():
    runtime_report = make_runtime(
        pytest_output=(
            "11 passed, 5 warnings in 0.36s"
        )
    )

    state = make_completed_state(
        runtime_report
    )

    snapshot = build_health_snapshot(
        state,
        sandbox_cleanup_ok=True,
    )

    assert snapshot[
        "status"
    ] == "ATTENTION"

    assert snapshot[
        "warn_count"
    ] >= 1

    assert snapshot[
        "fail_count"
    ] == 0

def test_warning_is_detected_without_numeric_count():
    snapshot = build_runtime_quality_snapshot(
        make_runtime(
            pytest_success=False,
            pytest_output=(
                "Runtime failure while preventing ResourceWarning "
                "from __del__."
            ),
        )
    )

    assert snapshot[
        "warning_count"
    ] == 0

    assert snapshot[
        "warning_detected"
    ] is True

    assert snapshot[
        "status"
    ] == "UNHEALTHY"


def test_runtime_quality_summary_reports_detected_warning():
    report = make_runtime(
        pytest_output=(
            "11 passed in 0.36s\n"
            "ResourceWarning: unclosed resource"
        )
    )

    summary = format_runtime_quality_summary(
        report
    )

    assert "ATTENTION" in summary
    assert "warnings detected" in summary


def test_runtime_history_records_failed_then_successful_attempt():
    state = ProjectState(
        request="Criar API FastAPI"
    )

    first = make_runtime(
        pytest_success=False,
        pytest_output=(
            "1 failed in 0.20s\n"
            "ResourceWarning: unclosed resource"
        ),
    )

    second = make_runtime(
        pytest_output=(
            "11 passed, 5 warnings in 0.44s"
        ),
    )

    record_runtime_attempt(
        state,
        first,
    )

    record_runtime_attempt(
        state,
        second,
    )

    assert len(
        state.runtime_history
    ) == 2

    assert state.runtime_history[
        0
    ][
        "quality_status"
    ] == "UNHEALTHY"

    assert state.runtime_history[
        1
    ][
        "quality_status"
    ] == "ATTENTION"

    assert runtime_recovered(
        state
    ) is True


def test_runtime_history_summary_marks_recovery():
    state = ProjectState(
        request="Criar API FastAPI"
    )

    record_runtime_attempt(
        state,
        make_runtime(
            pytest_success=False,
            pytest_output=(
                "1 failed in 0.20s"
            ),
        ),
    )

    record_runtime_attempt(
        state,
        make_runtime(
            pytest_output=(
                "11 passed in 0.44s"
            ),
        ),
    )

    summary = format_runtime_history_summary(
        state
    )

    assert "RECOVERED" in summary
    assert "#1 UNHEALTHY" in summary
    assert "#2 HEALTHY" in summary


def test_health_reports_runtime_recovered():
    final_runtime = make_runtime(
        pytest_output=(
            "11 passed, 5 warnings in 0.44s"
        )
    )

    state = make_completed_state(
        final_runtime
    )

    state.repair_attempts = 1

    record_runtime_attempt(
        state,
        make_runtime(
            pytest_success=False,
            pytest_output=(
                "1 failed in 0.20s"
            ),
        ),
    )

    record_runtime_attempt(
        state,
        final_runtime,
    )

    findings = evaluate_build_health(
        state,
        sandbox_cleanup_ok=True,
    )

    recovered = finding_by_code(
        findings,
        "runtime_recovered",
    )

    assert recovered.level == "PASS"
    assert "#1 UNHEALTHY" in recovered.message
    assert "#2 ATTENTION" in recovered.message
