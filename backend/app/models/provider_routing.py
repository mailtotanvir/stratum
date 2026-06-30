from typing import Any

from pydantic import BaseModel, Field


class ProviderRoutingRequest(BaseModel):
    requested_provider_id: str | None = Field(default=None)
    requested_model: str | None = Field(default=None)
    task_type: str | None = Field(default=None)
    budget_mode: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderRoutingDecision(BaseModel):
    provider_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    source: str = Field(min_length=1)
    adapter_provider_name: str | None = None
    base_url: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)
    enabled: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def provider(self) -> str:
        return self.provider_id


class ProviderRoutingResult(BaseModel):
    resolved: bool
    decision: ProviderRoutingDecision | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
