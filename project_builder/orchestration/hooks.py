from agents import RunHooks

from project_builder.models import ProjectContext
from project_builder.orchestration.orchestrator import (
    ProjectOrchestrator,
)
from project_builder.orchestration.state import (
    ProjectState,
)


class ProjectWorkflowHooks(
    RunHooks[ProjectContext]
):
    def __init__(
        self,
        state: ProjectState,
        orchestrator: ProjectOrchestrator,
    ) -> None:
        self.state = state
        self.orchestrator = orchestrator

    async def on_agent_start(
        self,
        context,
        agent,
    ) -> None:
        self.orchestrator.activate_agent(
            self.state,
            agent.name,
        )

        self.orchestrator.start_agent_usage(
            self.state,
            agent.name,
            context.usage,
        )

    async def on_handoff(
        self,
        context,
        from_agent,
        to_agent,
    ) -> None:
        self.orchestrator.finish_agent_usage(
            self.state,
            from_agent.name,
            context.usage,
        )

        self.orchestrator.record_handoff(
            self.state,
            from_agent.name,
            to_agent.name,
        )

    async def on_agent_end(
        self,
        context,
        agent,
        output,
    ) -> None:
        self.orchestrator.finish_agent_usage(
            self.state,
            agent.name,
            context.usage,
        )
