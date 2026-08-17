import pytest

from project_builder.orchestration.orchestrator import (
    ProjectOrchestrator,
)
from project_builder.orchestration.state import (
    ProjectStage,
    ProjectState,
)
from project_builder.request_gate import RequestGateResult


def test_request_gate_result_structured() -> None:
    result = RequestGateResult(
        status="UNSUPPORTED",
        reason="Frontend não é suportado.",
        unsupported_requirements=["React"],
    )

    assert result.status == "UNSUPPORTED"
    assert result.unsupported_requirements == ["React"]
    assert result.missing_information == []


def test_request_gate_implementable_flow() -> None:
    state = ProjectState(
        request="Crie uma API simples de inventário."
    )
    orchestrator = ProjectOrchestrator()

    orchestrator.transition(
        state,
        ProjectStage.REQUEST_VALIDATION,
    )
    orchestrator.transition(
        state,
        ProjectStage.ROUTING,
    )

    assert state.stage == ProjectStage.ROUTING
    assert state.transition_history == [
        "created -> request_validation",
        "request_validation -> routing",
    ]


def test_request_gate_can_stop_unsupported() -> None:
    state = ProjectState(
        request="Crie um frontend React."
    )
    orchestrator = ProjectOrchestrator()

    orchestrator.transition(
        state,
        ProjectStage.REQUEST_VALIDATION,
    )
    orchestrator.transition(
        state,
        ProjectStage.UNSUPPORTED,
    )

    assert state.stage == ProjectStage.UNSUPPORTED

    with pytest.raises(RuntimeError):
        orchestrator.transition(
            state,
            ProjectStage.ROUTING,
        )


def test_request_gate_can_stop_needs_input() -> None:
    state = ProjectState(
        request="SEU PEDIDO AQUI"
    )
    orchestrator = ProjectOrchestrator()

    orchestrator.transition(
        state,
        ProjectStage.REQUEST_VALIDATION,
    )
    orchestrator.transition(
        state,
        ProjectStage.NEEDS_INPUT,
    )

    assert state.stage == ProjectStage.NEEDS_INPUT


def test_created_to_routing_remains_backward_compatible() -> None:
    state = ProjectState(
        request="Criar uma API FastAPI"
    )
    orchestrator = ProjectOrchestrator()

    orchestrator.transition(
        state,
        ProjectStage.ROUTING,
    )

    assert state.stage == ProjectStage.ROUTING
    assert state.transition_history == [
        "created -> routing",
    ]
