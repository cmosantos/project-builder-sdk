from rich.console import Console

from project_builder.orchestration.performance import (
    build_agent_performance_rows,
    build_performance_panel,
    build_performance_snapshot,
    calculate_agent_durations,
    format_performance_summary,
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

    state.execution_events.extend(
        [
            ExecutionEvent(
                sequence=1,
                event_type="stage_transition",
                stage="request_validation",
                source="created",
                target="request_validation",
                elapsed_ms=5.0,
            ),
            ExecutionEvent(
                sequence=2,
                event_type="agent_activated",
                stage="request_validation",
                target="Request Gate",
                elapsed_ms=5.0,
            ),
            ExecutionEvent(
                sequence=3,
                event_type="stage_transition",
                stage="routing",
                source="request_validation",
                target="routing",
                elapsed_ms=100.0,
            ),
            ExecutionEvent(
                sequence=4,
                event_type="agent_activated",
                stage="routing",
                source="Request Gate",
                target="Project Router",
                elapsed_ms=10.0,
            ),
            ExecutionEvent(
                sequence=5,
                event_type="handoff",
                stage="routing",
                source="Project Router",
                target="Project Architect",
                elapsed_ms=200.0,
            ),
            ExecutionEvent(
                sequence=6,
                event_type="agent_activated",
                stage="routing",
                source="Project Router",
                target="Project Architect",
                elapsed_ms=5.0,
            ),
            ExecutionEvent(
                sequence=7,
                event_type="stage_transition",
                stage="development",
                source="routing",
                target="development",
                elapsed_ms=500.0,
            ),
            ExecutionEvent(
                sequence=8,
                event_type="agent_cleared",
                stage="runtime",
                source="Project Architect",
                elapsed_ms=5.0,
            ),
            ExecutionEvent(
                sequence=9,
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
                agent_name="Request Gate",
                stage="request_validation",
                requests=1,
                input_tokens=80,
                output_tokens=20,
                total_tokens=100,
            ),
            AgentUsageMetric(
                sequence=2,
                agent_name="Project Router",
                stage="routing",
                requests=2,
                input_tokens=250,
                output_tokens=50,
                total_tokens=300,
            ),
            AgentUsageMetric(
                sequence=3,
                agent_name="Project Architect",
                stage="routing",
                requests=1,
                input_tokens=150,
                output_tokens=50,
                total_tokens=200,
            ),
        ]
    )

    return state


def test_calculate_agent_durations_attributes_intervals():
    state = make_state()

    durations = calculate_agent_durations(
        state
    )

    assert durations[
        "Request Gate"
    ] == 110.0

    assert durations[
        "Project Router"
    ] == 205.0

    assert durations[
        "Project Architect"
    ] == 505.0


def test_build_agent_performance_rows_combines_time_and_usage():
    state = make_state()

    rows = build_agent_performance_rows(
        state
    )

    router = next(
        row
        for row in rows
        if row["agent_name"]
        == "Project Router"
    )

    assert router[
        "duration_ms"
    ] == 205.0

    assert router[
        "requests"
    ] == 2

    assert router[
        "total_tokens"
    ] == 300


def test_performance_snapshot_finds_different_hotspots():
    state = make_state()

    snapshot = build_performance_snapshot(
        state
    )

    assert snapshot[
        "slowest_agent"
    ] == "Project Architect"

    assert snapshot[
        "highest_usage_agent"
    ] == "Project Router"

    assert snapshot[
        "most_requests_agent"
    ] == "Project Router"


def test_performance_snapshot_tracks_non_agent_time():
    state = make_state()

    snapshot = build_performance_snapshot(
        state
    )

    assert snapshot[
        "total_duration_ms"
    ] == 930.0

    assert snapshot[
        "agent_duration_ms"
    ] == 820.0

    assert snapshot[
        "non_agent_duration_ms"
    ] == 110.0


def test_performance_snapshot_calculates_shares():
    state = make_state()

    snapshot = build_performance_snapshot(
        state
    )

    assert round(
        float(
            snapshot[
                "slowest_agent_share"
            ]
        ),
        1,
    ) == 54.3

    assert round(
        float(
            snapshot[
                "highest_usage_share"
            ]
        ),
        1,
    ) == 50.0


def test_format_performance_summary():
    state = make_state()

    summary = format_performance_summary(
        state
    )

    assert "Project Architect" in summary
    assert "Project Router" in summary
    assert "300 tokens" in summary


def test_performance_panel_renders():
    state = make_state()

    panel = build_performance_panel(
        state
    )

    console = Console(
        record=True,
        width=160,
    )

    console.print(
        panel
    )

    output = console.export_text()

    assert "BUILD PERFORMANCE" in output
    assert "Slowest agent" in output
    assert "Highest usage" in output
    assert "Project Architect" in output
    assert "Project Router" in output