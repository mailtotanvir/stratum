from app.models.planner import PlannerRequest
from app.models.tool import Tool, ToolParameter
from app.services.cognitive_state_service import (
    CognitiveStateService,
    cognitive_state_service,
)
from app.services.planning_context_service import (
    PlanningContextService,
    planning_context_service,
)
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)
from app.services.tool_registry_service import (
    ToolRegistryService,
    tool_registry_service,
)


class PlannerInputBuilderService:
    def __init__(
        self,
        sessions: RuntimeSessionService | None = None,
        planning_context: PlanningContextService | None = None,
        cognitive_state: CognitiveStateService | None = None,
        tools: ToolRegistryService | None = None,
    ) -> None:
        self._sessions = sessions or runtime_session_service
        self._planning_context = planning_context or planning_context_service
        self._cognitive_state = cognitive_state or cognitive_state_service
        self._tools = tools or tool_registry_service

    def build(self, session_id: str, objective: str) -> PlannerRequest:
        session = self._sessions.get_session(session_id)
        planning_context = self._planning_context.build(session_id)
        cognitive_state = self._cognitive_state.build(
            session_id,
            planning_context=planning_context,
        )
        available_tools = [
            self._to_tool(record)
            for record in sorted(
                self._tools.list_tools(enabled_only=True),
                key=lambda record: (record.name, record.id),
            )
        ]

        return PlannerRequest(
            task_id=session.task_id,
            session_id=session.id,
            objective=objective,
            available_tools=available_tools,
            context={
                "context_source": "planning_context",
                "planning_context": planning_context.model_dump(mode="json"),
            },
            cognitive_state=cognitive_state,
        )

    def _to_tool(self, record) -> Tool:
        return Tool(
            id=record.id,
            name=record.name,
            description=record.description,
            enabled=record.enabled,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
            parameters=[
                ToolParameter(
                    id=parameter.id,
                    tool_id=parameter.tool_id,
                    name=parameter.name,
                    type=parameter.type,
                    required=parameter.required,
                )
                for parameter in self._tools.list_parameters(record.id)
            ],
        )


planner_input_builder_service = PlannerInputBuilderService()
