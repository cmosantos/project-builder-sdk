import pytest

from project_builder.orchestration.orchestrator import (
    ProjectOrchestrator,
)
from project_builder.orchestration.state import (
    ProjectStage,
    ProjectState,
)


def test_project_state_starts_created():
    state = ProjectState(
        request="Criar uma API FastAPI"
    )

    assert state.stage is ProjectStage.CREATED
    assert state.repair_attempts == 0
    assert state.current_agent is None
    assert state.previous_agent is None

    assert state.transition_history == []
    assert state.handoff_history == []
    assert state.execution_events == []
    assert state.errors == []


def test_orchestrator_transitions_stage():
    state = ProjectState(
        request="Criar uma API FastAPI"
    )

    orchestrator = ProjectOrchestrator()

    orchestrator.transition(
        state,
        ProjectStage.ROUTING,
    )

    assert state.stage is ProjectStage.ROUTING

    assert state.transition_history == [
        "created -> routing"
    ]

    assert len(state.execution_events) == 1

    event = state.execution_events[0]

    assert event.sequence == 1
    assert event.event_type == "stage_transition"
    assert event.stage == "routing"
    assert event.source == "created"
    assert event.target == "routing"

    assert event.details == {
        "from_stage": "created",
        "to_stage": "routing",
    }


def test_orchestrator_activates_agent():
    state = ProjectState(
        request="Criar uma API FastAPI"
    )

    orchestrator = ProjectOrchestrator()

    orchestrator.activate_agent(
        state,
        "Project Router",
    )

    assert state.current_agent == "Project Router"
    assert state.previous_agent is None

    orchestrator.activate_agent(
        state,
        "Project Architect",
    )

    assert state.current_agent == "Project Architect"
    assert state.previous_agent == "Project Router"

    assert [
        event.event_type
        for event in state.execution_events
    ] == [
        "agent_activated",
        "agent_activated",
    ]

    assert state.execution_events[0].target == (
        "Project Router"
    )

    assert state.execution_events[1].source == (
        "Project Router"
    )

    assert state.execution_events[1].target == (
        "Project Architect"
    )


def test_orchestrator_records_real_handoff():
    state = ProjectState(
        request="Criar uma API FastAPI"
    )

    orchestrator = ProjectOrchestrator()

    orchestrator.record_handoff(
        state,
        "Project Router",
        "Project Architect",
    )

    assert state.handoff_history == [
        "Project Router -> Project Architect"
    ]

    assert len(state.execution_events) == 1

    event = state.execution_events[0]

    assert event.sequence == 1
    assert event.event_type == "handoff"
    assert event.source == "Project Router"
    assert event.target == "Project Architect"


def test_execution_timeline_preserves_event_order():
    state = ProjectState(
        request="Criar uma API FastAPI"
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

    assert [
        event.sequence
        for event in state.execution_events
    ] == [
        1,
        2,
        3,
        4,
    ]

    assert [
        event.event_type
        for event in state.execution_events
    ] == [
        "stage_transition",
        "agent_activated",
        "handoff",
        "agent_activated",
    ]


def test_repeated_agent_activation_is_not_duplicated():
    state = ProjectState(
        request="Criar uma API FastAPI"
    )

    orchestrator = ProjectOrchestrator()

    orchestrator.activate_agent(
        state,
        "Project Router",
    )

    orchestrator.activate_agent(
        state,
        "Project Router",
    )

    assert len(state.execution_events) == 1

    assert (
        state.execution_events[0].event_type
        == "agent_activated"
    )


def test_orchestrator_rejects_invalid_transition():
    state = ProjectState(
        request="Criar uma API FastAPI"
    )

    orchestrator = ProjectOrchestrator()

    with pytest.raises(
        RuntimeError,
        match="Transição inválida",
    ):
        orchestrator.transition(
            state,
            ProjectStage.QA,
        )


def test_begin_repair_updates_state():
    state = ProjectState(
        request="Criar uma API FastAPI"
    )

    orchestrator = ProjectOrchestrator()

    orchestrator.transition(
        state,
        ProjectStage.ROUTING,
    )

    orchestrator.transition(
        state,
        ProjectStage.DEVELOPMENT,
    )

    orchestrator.transition(
        state,
        ProjectStage.QA,
    )

    orchestrator.begin_repair(
        state,
        origin="QA",
    )

    assert state.stage is ProjectStage.REPAIR
    assert state.repair_attempts == 1
    assert state.current_agent == "Project Repair"

    assert (
        "repair #1 origin=QA"
        in state.transition_history
    )

    repair_events = [
        event
        for event in state.execution_events
        if event.event_type == "repair_attempt"
    ]

    assert len(repair_events) == 1

    event = repair_events[0]

    assert event.source == "QA"
    assert event.target == "Project Repair"

    assert event.details == {
        "attempt": 1,
        "origin": "QA",
    }