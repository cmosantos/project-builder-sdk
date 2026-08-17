from types import SimpleNamespace

from rich.console import Console

from project_builder.orchestration.orchestrator import (
    ProjectOrchestrator,
)
from project_builder.orchestration.state import (
    AgentUsageMetric,
    ProjectStage,
    ProjectState,
)
from project_builder.orchestration.usage import (
    aggregate_agent_usage,
    build_agent_usage_panel,
    format_usage_summary,
    usage_totals,
)


def make_usage(
    *,
    requests: int,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    reasoning_tokens: int = 0,
):
    return SimpleNamespace(
        requests=requests,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=(
            input_tokens
            + output_tokens
        ),
        input_tokens_details=SimpleNamespace(
            cached_tokens=cached_tokens
        ),
        output_tokens_details=SimpleNamespace(
            reasoning_tokens=reasoning_tokens
        ),
    )


def test_agent_usage_records_delta():
    state = ProjectState(
        request="Criar API FastAPI"
    )

    orchestrator = ProjectOrchestrator()

    orchestrator.transition(
        state,
        ProjectStage.ROUTING,
    )

    orchestrator.start_agent_usage(
        state,
        "Project Router",
        make_usage(
            requests=1,
            input_tokens=100,
            output_tokens=20,
        ),
    )

    metric = orchestrator.finish_agent_usage(
        state,
        "Project Router",
        make_usage(
            requests=2,
            input_tokens=350,
            output_tokens=70,
        ),
    )

    assert metric is not None
    assert metric.requests == 1
    assert metric.input_tokens == 250
    assert metric.output_tokens == 50
    assert metric.total_tokens == 300


def test_agent_usage_preserves_cached_and_reasoning_tokens():
    state = ProjectState(
        request="Criar API FastAPI"
    )

    orchestrator = ProjectOrchestrator()

    orchestrator.start_agent_usage(
        state,
        "Project Architect",
        make_usage(
            requests=0,
            input_tokens=0,
            output_tokens=0,
        ),
    )

    metric = orchestrator.finish_agent_usage(
        state,
        "Project Architect",
        make_usage(
            requests=1,
            input_tokens=500,
            output_tokens=100,
            cached_tokens=120,
            reasoning_tokens=30,
        ),
    )

    assert metric is not None
    assert metric.cached_tokens == 120
    assert metric.reasoning_tokens == 30


def test_finish_agent_usage_does_not_duplicate():
    state = ProjectState(
        request="Criar API FastAPI"
    )

    orchestrator = ProjectOrchestrator()

    orchestrator.start_agent_usage(
        state,
        "Project Developer",
        make_usage(
            requests=0,
            input_tokens=0,
            output_tokens=0,
        ),
    )

    first = orchestrator.finish_agent_usage(
        state,
        "Project Developer",
        make_usage(
            requests=1,
            input_tokens=100,
            output_tokens=50,
        ),
    )

    second = orchestrator.finish_agent_usage(
        state,
        "Project Developer",
        make_usage(
            requests=1,
            input_tokens=100,
            output_tokens=50,
        ),
    )

    assert first is not None
    assert second is None
    assert len(state.agent_usage) == 1


def test_aggregate_agent_usage_combines_repeated_runs():
    state = ProjectState(
        request="Criar API FastAPI"
    )

    state.agent_usage.extend(
        [
            AgentUsageMetric(
                sequence=1,
                agent_name="Project QA",
                stage="qa",
                requests=1,
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
            ),
            AgentUsageMetric(
                sequence=2,
                agent_name="Project QA",
                stage="qa",
                requests=1,
                input_tokens=200,
                output_tokens=30,
                total_tokens=230,
            ),
        ]
    )

    items = aggregate_agent_usage(
        state
    )

    assert len(items) == 1

    qa = items[0]

    assert qa["runs"] == 2
    assert qa["requests"] == 2
    assert qa["total_tokens"] == 350


def test_usage_totals_and_summary():
    state = ProjectState(
        request="Criar API FastAPI"
    )

    state.agent_usage.append(
        AgentUsageMetric(
            sequence=1,
            agent_name="Request Gate",
            stage="request_validation",
            requests=1,
            input_tokens=1000,
            output_tokens=200,
            total_tokens=1200,
        )
    )

    totals = usage_totals(
        state
    )

    assert totals["requests"] == 1
    assert totals["total_tokens"] == 1200

    summary = format_usage_summary(
        state
    )

    assert "1 req" in summary
    assert "1.200 total" in summary


def test_agent_usage_panel_renders_agents():
    state = ProjectState(
        request="Criar API FastAPI"
    )

    state.agent_usage.append(
        AgentUsageMetric(
            sequence=1,
            agent_name="Project Architect",
            stage="routing",
            requests=1,
            input_tokens=1500,
            output_tokens=300,
            total_tokens=1800,
        )
    )

    panel = build_agent_usage_panel(
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

    assert "AGENT USAGE" in output
    assert "Project Architect" in output
    assert "1.800" in output
