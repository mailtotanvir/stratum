from app.models.agent_execution import (
    AgentExecutionMode,
    AgentExecutionStatus,
)
from app.models.agent_execution_diagnostics import AgentExecutionDiagnostics
from app.services.agent_execution_service import (
    AgentExecutionService,
    agent_execution_service,
)
from app.services.provider_execution_diagnostics_service import (
    ProviderExecutionDiagnosticsService,
    provider_execution_diagnostics_service,
)
from app.services.provider_execution_service import (
    ProviderExecutionService,
    provider_execution_service,
)


class AgentExecutionDiagnosticsService:
    def __init__(
        self,
        agent_service: AgentExecutionService | None = None,
        provider_service: ProviderExecutionService | None = None,
        provider_diagnostics: ProviderExecutionDiagnosticsService | None = None,
    ) -> None:
        self._agent_service = agent_service or agent_execution_service
        self._provider_service = (
            provider_service or provider_execution_service
        )
        self._provider_diagnostics = (
            provider_diagnostics or provider_execution_diagnostics_service
        )

    def get_diagnostics(self) -> AgentExecutionDiagnostics:
        provider_diagnostics_available = callable(
            getattr(self._provider_diagnostics, "get_diagnostics", None)
        )
        mock_provider_available = False
        if provider_diagnostics_available:
            mock_provider_available = (
                self._provider_diagnostics.get_diagnostics()
                .mock_provider_available
            )

        return AgentExecutionDiagnostics(
            agent_execution_service_ready=callable(
                getattr(self._agent_service, "execute", None)
            ),
            provider_execution_service_ready=callable(
                getattr(self._provider_service, "execute", None)
            ),
            provider_diagnostics_available=provider_diagnostics_available,
            supported_agent_modes=[
                mode.value for mode in AgentExecutionMode
            ],
            supported_agent_statuses=[
                status.value for status in AgentExecutionStatus
            ],
            mock_provider_available=mock_provider_available,
            warnings=[],
            metadata={},
        )


agent_execution_diagnostics_service = AgentExecutionDiagnosticsService()
