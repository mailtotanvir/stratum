from typing import Any

from pydantic import BaseModel, Field


class ProviderRoutingDecision(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    adapter_provider_name: str = Field(min_length=1)
    base_url: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)
    enabled: bool
    reason: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderRoutingResult(BaseModel):
    resolved: bool
    decision: ProviderRoutingDecision | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
