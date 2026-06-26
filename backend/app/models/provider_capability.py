from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ProviderCapabilityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class ProviderModelCapability(StrEnum):
    CHAT = "chat"
    COMPLETION = "completion"
    TOOL_CALL = "tool_call"
    STREAMING = "streaming"
    JSON_OUTPUT = "json_output"


class ProviderModelDescriptor(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    display_name: str | None = None
    status: ProviderCapabilityStatus = ProviderCapabilityStatus.AVAILABLE
    capabilities: list[ProviderModelCapability] = Field(min_length=1)
    context_window: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    cost_per_1k_input_tokens: float | None = Field(default=None, ge=0)
    cost_per_1k_output_tokens: float | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider", "model")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class ProviderRegistrySnapshot(BaseModel):
    providers: list[str]
    models: list[ProviderModelDescriptor]
    metadata: dict[str, Any] = Field(default_factory=dict)
