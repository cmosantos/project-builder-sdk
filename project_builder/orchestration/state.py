from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from time import perf_counter
from typing import Any

from project_builder.models import ProjectContext


class ProjectStage(str, Enum):
    CREATED = "created"
    REQUEST_VALIDATION = "request_validation"
    ROUTING = "routing"
    DEVELOPMENT = "development"
    QA = "qa"
    REPAIR = "repair"
    RUNTIME = "runtime"
    COMPLETED = "completed"
    NEEDS_INPUT = "needs_input"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


@dataclass
class ExecutionEvent:
    sequence: int
    event_type: str
    stage: str

    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    elapsed_ms: float = 0.0

    source: str | None = None
    target: str | None = None

    details: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class UsageSnapshot:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0


@dataclass
class AgentUsageMetric:
    sequence: int
    agent_name: str
    stage: str

    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int

    cached_tokens: int = 0
    reasoning_tokens: int = 0


@dataclass
class ProjectState:
    request: str
    build_id: str | None = None

    context: ProjectContext = field(
        default_factory=ProjectContext
    )

    stage: ProjectStage = ProjectStage.CREATED

    request_gate_status: str | None = None
    request_gate_reason: str | None = None

    current_agent: str | None = None
    previous_agent: str | None = None

    repair_attempts: int = 0

    transition_history: list[str] = field(
        default_factory=list
    )

    handoff_history: list[str] = field(
        default_factory=list
    )

    execution_events: list[ExecutionEvent] = field(
        default_factory=list
    )

    agent_usage: list[AgentUsageMetric] = field(
        default_factory=list
    )

    runtime_history: list[
        dict[str, Any]
    ] = field(
        default_factory=list
    )

    errors: list[str] = field(
        default_factory=list
    )

    execution_started_at: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    _last_event_monotonic: float = field(
        default_factory=perf_counter,
        repr=False,
    )

    _agent_usage_baselines: dict[
        str,
        UsageSnapshot,
    ] = field(
        default_factory=dict,
        repr=False,
    )

    _agent_usage_stages: dict[
        str,
        str,
    ] = field(
        default_factory=dict,
        repr=False,
    )

    def __post_init__(
        self,
    ) -> None:
        """
        Mantém o pedido recebido pelo workflow dentro do
        ProjectContext durante toda a execução.

        Se um contexto já vier associado a outro pedido,
        a execução é rejeitada para impedir mistura de
        contratos entre projetos.
        """

        if not self.context.original_request:
            self.context.original_request = self.request
            return

        if self.context.original_request != self.request:
            raise ValueError(
                "ProjectContext pertence a um pedido "
                "original diferente."
            )