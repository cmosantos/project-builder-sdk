from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from agents.tracing import (
    custom_span,
    get_current_trace,
)

from project_builder.orchestration.state import (
    AgentUsageMetric,
    ExecutionEvent,
    ProjectStage,
    ProjectState,
    UsageSnapshot,
)


_ALLOWED_TRANSITIONS: dict[
    ProjectStage,
    set[ProjectStage],
] = {
    ProjectStage.CREATED: {
        ProjectStage.REQUEST_VALIDATION,
        ProjectStage.ROUTING,
    },
    ProjectStage.REQUEST_VALIDATION: {
        ProjectStage.ROUTING,
        ProjectStage.NEEDS_INPUT,
        ProjectStage.UNSUPPORTED,
        ProjectStage.FAILED,
    },
    ProjectStage.ROUTING: {
        ProjectStage.DEVELOPMENT,
        ProjectStage.FAILED,
    },
    ProjectStage.DEVELOPMENT: {
        ProjectStage.QA,
        ProjectStage.FAILED,
    },
    ProjectStage.QA: {
        ProjectStage.REPAIR,
        ProjectStage.RUNTIME,
        ProjectStage.FAILED,
    },
    ProjectStage.REPAIR: {
        ProjectStage.QA,
        ProjectStage.FAILED,
    },
    ProjectStage.RUNTIME: {
        ProjectStage.REPAIR,
        ProjectStage.COMPLETED,
        ProjectStage.FAILED,
    },
    ProjectStage.COMPLETED: set(),
    ProjectStage.NEEDS_INPUT: set(),
    ProjectStage.UNSUPPORTED: set(),
    ProjectStage.FAILED: set(),
}


def _trace_event(
    name: str,
    data: dict[str, object],
) -> None:
    if get_current_trace() is None:
        return

    with custom_span(
        name,
        data,
    ):
        pass


def _safe_int(
    value: Any,
) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _usage_snapshot(
    usage: Any,
) -> UsageSnapshot:
    if usage is None:
        return UsageSnapshot()

    input_details = getattr(
        usage,
        "input_tokens_details",
        None,
    )

    output_details = getattr(
        usage,
        "output_tokens_details",
        None,
    )

    input_tokens = _safe_int(
        getattr(
            usage,
            "input_tokens",
            0,
        )
    )

    output_tokens = _safe_int(
        getattr(
            usage,
            "output_tokens",
            0,
        )
    )

    total_tokens = _safe_int(
        getattr(
            usage,
            "total_tokens",
            0,
        )
    )

    if total_tokens == 0:
        total_tokens = (
            input_tokens
            + output_tokens
        )

    return UsageSnapshot(
        requests=_safe_int(
            getattr(
                usage,
                "requests",
                0,
            )
        ),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_tokens=_safe_int(
            getattr(
                input_details,
                "cached_tokens",
                0,
            )
        ),
        reasoning_tokens=_safe_int(
            getattr(
                output_details,
                "reasoning_tokens",
                0,
            )
        ),
    )


def _usage_delta(
    current: UsageSnapshot,
    baseline: UsageSnapshot,
) -> UsageSnapshot:
    return UsageSnapshot(
        requests=max(
            current.requests
            - baseline.requests,
            0,
        ),
        input_tokens=max(
            current.input_tokens
            - baseline.input_tokens,
            0,
        ),
        output_tokens=max(
            current.output_tokens
            - baseline.output_tokens,
            0,
        ),
        total_tokens=max(
            current.total_tokens
            - baseline.total_tokens,
            0,
        ),
        cached_tokens=max(
            current.cached_tokens
            - baseline.cached_tokens,
            0,
        ),
        reasoning_tokens=max(
            current.reasoning_tokens
            - baseline.reasoning_tokens,
            0,
        ),
    )


def _record_execution_event(
    state: ProjectState,
    event_type: str,
    *,
    source: str | None = None,
    target: str | None = None,
    details: dict[str, object] | None = None,
) -> ExecutionEvent:
    now_monotonic = perf_counter()

    elapsed_ms = max(
        (
            now_monotonic
            - state._last_event_monotonic
        )
        * 1000.0,
        0.0,
    )

    state._last_event_monotonic = now_monotonic

    event = ExecutionEvent(
        sequence=len(state.execution_events) + 1,
        event_type=event_type,
        stage=state.stage.value,
        occurred_at=datetime.now(
            timezone.utc
        ),
        elapsed_ms=round(
            elapsed_ms,
            2,
        ),
        source=source,
        target=target,
        details=dict(details or {}),
    )

    state.execution_events.append(event)

    return event


class ProjectOrchestrator:
    def transition(
        self,
        state: ProjectState,
        next_stage: ProjectStage,
    ) -> ProjectState:
        if state.stage == next_stage:
            return state

        allowed = _ALLOWED_TRANSITIONS[state.stage]

        if next_stage not in allowed:
            raise RuntimeError(
                "Transição inválida do workflow: "
                f"{state.stage.value} -> {next_stage.value}"
            )

        previous_stage = state.stage
        state.stage = next_stage

        state.transition_history.append(
            f"{previous_stage.value} -> {next_stage.value}"
        )

        event = _record_execution_event(
            state,
            "stage_transition",
            source=previous_stage.value,
            target=next_stage.value,
            details={
                "from_stage": previous_stage.value,
                "to_stage": next_stage.value,
            },
        )

        _trace_event(
            "project_stage_transition",
            {
                "from_stage": previous_stage.value,
                "to_stage": next_stage.value,
                "elapsed_ms": event.elapsed_ms,
            },
        )

        return state

    def activate_agent(
        self,
        state: ProjectState,
        agent_name: str,
    ) -> ProjectState:
        if state.current_agent == agent_name:
            return state

        previous_agent = state.current_agent

        state.previous_agent = previous_agent
        state.current_agent = agent_name

        event = _record_execution_event(
            state,
            "agent_activated",
            source=previous_agent,
            target=agent_name,
        )

        _trace_event(
            "project_agent_activation",
            {
                "previous_agent": previous_agent,
                "agent": agent_name,
                "stage": state.stage.value,
                "elapsed_ms": event.elapsed_ms,
            },
        )

        return state

    def clear_agent(
        self,
        state: ProjectState,
    ) -> ProjectState:
        if state.current_agent is None:
            return state

        previous_agent = state.current_agent

        state.previous_agent = previous_agent
        state.current_agent = None

        event = _record_execution_event(
            state,
            "agent_cleared",
            source=previous_agent,
        )

        _trace_event(
            "project_agent_cleared",
            {
                "agent": previous_agent,
                "stage": state.stage.value,
                "elapsed_ms": event.elapsed_ms,
            },
        )

        return state

    def record_handoff(
        self,
        state: ProjectState,
        source_agent: str,
        target_agent: str,
    ) -> ProjectState:
        state.handoff_history.append(
            f"{source_agent} -> {target_agent}"
        )

        event = _record_execution_event(
            state,
            "handoff",
            source=source_agent,
            target=target_agent,
        )

        _trace_event(
            "project_agent_handoff",
            {
                "source_agent": source_agent,
                "target_agent": target_agent,
                "stage": state.stage.value,
                "elapsed_ms": event.elapsed_ms,
            },
        )

        return state

    def start_agent_usage(
        self,
        state: ProjectState,
        agent_name: str,
        usage: Any,
    ) -> ProjectState:
        state._agent_usage_baselines[
            agent_name
        ] = _usage_snapshot(
            usage
        )

        state._agent_usage_stages[
            agent_name
        ] = state.stage.value

        return state

    def finish_agent_usage(
        self,
        state: ProjectState,
        agent_name: str,
        usage: Any,
    ) -> AgentUsageMetric | None:
        baseline = state._agent_usage_baselines.pop(
            agent_name,
            None,
        )

        stage = state._agent_usage_stages.pop(
            agent_name,
            state.stage.value,
        )

        if baseline is None:
            return None

        current = _usage_snapshot(
            usage
        )

        delta = _usage_delta(
            current,
            baseline,
        )

        metric = AgentUsageMetric(
            sequence=len(state.agent_usage) + 1,
            agent_name=agent_name,
            stage=stage,
            requests=delta.requests,
            input_tokens=delta.input_tokens,
            output_tokens=delta.output_tokens,
            total_tokens=delta.total_tokens,
            cached_tokens=delta.cached_tokens,
            reasoning_tokens=delta.reasoning_tokens,
        )

        state.agent_usage.append(
            metric
        )

        _trace_event(
            "project_agent_usage",
            {
                "agent": agent_name,
                "stage": stage,
                "requests": metric.requests,
                "input_tokens": metric.input_tokens,
                "output_tokens": metric.output_tokens,
                "total_tokens": metric.total_tokens,
                "cached_tokens": metric.cached_tokens,
                "reasoning_tokens": metric.reasoning_tokens,
            },
        )

        return metric

    def begin_repair(
        self,
        state: ProjectState,
        origin: str,
    ) -> ProjectState:
        self.transition(
            state,
            ProjectStage.REPAIR,
        )

        state.repair_attempts += 1

        self.activate_agent(
            state,
            "Project Repair",
        )

        state.transition_history.append(
            f"repair #{state.repair_attempts} origin={origin}"
        )

        event = _record_execution_event(
            state,
            "repair_attempt",
            source=origin,
            target="Project Repair",
            details={
                "attempt": state.repair_attempts,
                "origin": origin,
            },
        )

        _trace_event(
            "project_repair_attempt",
            {
                "attempt": state.repair_attempts,
                "origin": origin,
                "elapsed_ms": event.elapsed_ms,
            },
        )

        return state

    def fail(
        self,
        state: ProjectState,
        error: str,
    ) -> ProjectState:
        if error:
            state.errors.append(error)

        active_agent = state.current_agent

        if state.stage not in (
            ProjectStage.COMPLETED,
            ProjectStage.NEEDS_INPUT,
            ProjectStage.UNSUPPORTED,
            ProjectStage.FAILED,
        ):
            previous_stage = state.stage
            state.stage = ProjectStage.FAILED

            state.transition_history.append(
                f"{previous_stage.value} -> failed"
            )

        event = _record_execution_event(
            state,
            "failure",
            source=active_agent,
            target=ProjectStage.FAILED.value,
            details={
                "error": error,
            },
        )

        self.clear_agent(state)

        _trace_event(
            "project_failure",
            {
                "stage": state.stage.value,
                "error": error,
                "elapsed_ms": event.elapsed_ms,
            },
        )

        return state
