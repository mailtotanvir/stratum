from app.models.provider_routing import (
    ProviderRoutingDecision,
    ProviderRoutingRequest,
)
from app.services.provider_configuration_service import (
    ProviderConfigurationService,
    provider_configuration_service,
)


class ProviderRoutingPolicyService:
    def __init__(
        self,
        configurations: ProviderConfigurationService | None = None,
    ) -> None:
        self._configurations = (
            configurations or provider_configuration_service
        )

    def resolve(
        self,
        request: ProviderRoutingRequest,
    ) -> ProviderRoutingDecision:
        if request.requested_provider_id and request.requested_model:
            return self._explicit_decision(request)
        provider_id, source = self._resolve_provider_id(request)
        configuration = self._configurations.get(provider_id)
        model = self._resolve_model(configuration.default_model, request)
        return ProviderRoutingDecision(
            provider_id=provider_id,
            model=model,
            reason=source,
            source=source,
            adapter_provider_name=configuration.api_style,
            base_url=configuration.base_url,
            timeout_seconds=configuration.timeout_seconds,
            enabled=configuration.enabled,
            metadata={
                "task_type": request.task_type,
                "budget_mode": request.budget_mode,
                "requested_provider_id": request.requested_provider_id,
                "requested_model": request.requested_model,
            },
        )

    def _explicit_decision(
        self,
        request: ProviderRoutingRequest,
    ) -> ProviderRoutingDecision:
        provider_id = request.requested_provider_id or self._default_provider_id()
        configuration = (
            self._configurations.get(provider_id)
            if self._configurations.exists(provider_id)
            else None
        )
        return ProviderRoutingDecision(
            provider_id=provider_id,
            model=request.requested_model or (configuration.default_model if configuration else ""),
            reason="explicit_request",
            source="explicit_request",
            adapter_provider_name=(
                configuration.api_style if configuration is not None else None
            ),
            base_url=configuration.base_url if configuration else None,
            timeout_seconds=(
                configuration.timeout_seconds if configuration else None
            ),
            enabled=configuration.enabled if configuration else None,
            metadata={
                "task_type": request.task_type,
                "budget_mode": request.budget_mode,
                "requested_provider_id": request.requested_provider_id,
                "requested_model": request.requested_model,
            },
        )

    def _resolve_provider_id(
        self,
        request: ProviderRoutingRequest,
    ) -> tuple[str, str]:
        requested_provider_id = request.requested_provider_id
        if requested_provider_id and self._configurations.exists(
            requested_provider_id
        ):
            configuration = self._configurations.get(requested_provider_id)
            if configuration.enabled:
                return requested_provider_id, "explicit_request"
        default_provider = self._default_provider_id()
        return default_provider, "default_configuration"

    def _resolve_model(
        self,
        default_model: str | None,
        request: ProviderRoutingRequest,
    ) -> str:
        requested_model = request.requested_model
        if requested_model and self._model_is_valid(
            request.requested_provider_id,
            requested_model,
        ):
            return requested_model
        if default_model is not None:
            return default_model
        return requested_model or ""

    def _model_is_valid(
        self,
        provider_id: str | None,
        model: str,
    ) -> bool:
        if provider_id is None or not self._configurations.exists(provider_id):
            return False
        configuration = self._configurations.get(provider_id)
        if configuration.available_models:
            return model in configuration.available_models
        return configuration.default_model == model

    def _default_provider_id(self) -> str:
        for configuration in self._configurations.list_configurations():
            if configuration.enabled and configuration.default_model is not None:
                return configuration.provider_id
        for configuration in self._configurations.list_configurations():
            if configuration.enabled:
                return configuration.provider_id
        return self._configurations.list_configurations()[0].provider_id


provider_routing_policy_service = ProviderRoutingPolicyService()
