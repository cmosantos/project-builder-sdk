from rich.console import Console

from project_builder.orchestration.orchestrator import (
    ProjectOrchestrator,
)
from project_builder.orchestration.state import (
    ExecutionEvent,
    ProjectStage,
    ProjectState,
)
from project_builder.orchestration.timeline import (
    build_execution_timeline,
    format_event_flow,
    render_execution_timeline,
)


def test_format_stage_transition():
    event = ExecutionEvent(
        sequence=1,
        event_type="stage_transition",
        stage="routing",
        source="created",
        target="routing",
    )

    assert format_event_flow(event) == (
        "created -> routing"
    )


def test_format_handoff():
    event = ExecutionEvent(
        sequence=1,
        event_type="handoff",
        stage="routing",
        source="Project Router",
        target="Project Architect",
    )

    assert format_event_flow(event) == (
        "Project Router -> Project Architect"
    )


def test_format_agent_activation():
    event = ExecutionEvent(
        sequence=1,
        event_type="agent_activated",
        stage="routing",
        target="Project Router",
    )

    assert format_event_flow(event) == (
        "Project Router"
    )


def test_format_repair_attempt():
    event = ExecutionEvent(
        sequence=1,
        event_type="repair_attempt",
        stage="repair",
        source="QA",
        target="Project Repair",
        details={
            "attempt": 2,
            "origin": "QA",
        },
    )

    assert format_event_flow(event) == (
        "repair #2 origin=QA"
    )


def test_build_timeline_returns_panel():
    state = ProjectState(
        request="Criar API FastAPI",
        build_id="build-123",
    )

    orchestrator = ProjectOrchestrator()

    orchestrator.transition(
        state,
        ProjectStage.ROUTING,
    )

    orchestrator.activate_agent(
        state,
        "Project Router",
    )

    panel = build_execution_timeline(
        state
    )

    assert panel is not None


def test_render_execution_timeline():
    state = ProjectState(
        request="Criar API FastAPI",
        build_id="build-123",
    )

    orchestrator = ProjectOrchestrator()

    orchestrator.transition(
        state,
        ProjectStage.ROUTING,
    )

    orchestrator.activate_agent(
        state,
        "Project Router",
    )

    orchestrator.record_handoff(
        state,
        "Project Router",
        "Project Architect",
    )

    orchestrator.activate_agent(
        state,
        "Project Architect",
    )

    console = Console(
        record=True,
        width=160,
    )

    render_execution_timeline(
        console,
        state,
    )

    output = console.export_text()

    assert "EXECUTION TIMELINE" in output
    assert "stage_transition" in output
    assert "agent_activated" in output
    assert "handoff" in output

    assert (
        "Project Router -> Project Architect"
        in output
    )