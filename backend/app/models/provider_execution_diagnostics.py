from typing import Literal

from pydantic import BaseModel, Field

from app.models.provider_capability import ProviderModelDescriptor


ProviderExecutionReadinessStatus = Literal["ready", "unavailable"]


class ProviderExecutionDiagnostics(BaseModel):
    registered_provider_adapters: list[str]
    supported_adapter_models: dict[str, list[str]]
    capability_registry_providers: list[str]
    capability_registry_models: list[ProviderModelDescriptor]
    mock_provider_available: bool
    mock_capability_descriptors_exist: bool
    validator_status: ProviderExecutionReadinessStatus
    execution_service_status: ProviderExecutionReadinessStatus
    warnings: list[str] = Field(default_factory=list)
