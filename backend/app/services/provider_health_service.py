from app.models.provider_health import ProviderHealth
from app.services.provider_live_diagnostics_service import (
    provider_live_diagnostics_service,
)


class ProviderHealthService:
    def health(self) -> ProviderHealth:
        diagnostics = provider_live_diagnostics_service.inspect_environment()

        if not diagnostics.configured:
            status = "unconfigured"
        elif diagnostics.ready:
            status = "ready"
        else:
            status = "configuration_error"

        return ProviderHealth(
            provider_id=diagnostics.provider_id,
            ready=diagnostics.ready,
            configured=diagnostics.configured,
            enabled=diagnostics.enabled,
            supports_completion=diagnostics.ready,
            supports_streaming=diagnostics.supports_streaming,
            status=status,
        )


provider_health_service = ProviderHealthService()
