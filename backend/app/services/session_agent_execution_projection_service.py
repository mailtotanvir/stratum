from app.models.session_agent_execution_projection import (
    SessionAgentExecutionProjection,
)
from app.services.session_agent_execution_projection_builder_service import (
    SessionAgentExecutionProjectionBuilderService,
    session_agent_execution_projection_builder_service,
)


class SessionAgentExecutionProjectionService:
    def __init__(
        self,
        builder: SessionAgentExecutionProjectionBuilderService | None = None,
    ) -> None:
        self._builder = (
            builder or session_agent_execution_projection_builder_service
        )

    def get_projection(
        self,
        runtime_session_id: str,
    ) -> SessionAgentExecutionProjection:
        return self._builder.build(runtime_session_id)


session_agent_execution_projection_service = (
    SessionAgentExecutionProjectionService()
)
