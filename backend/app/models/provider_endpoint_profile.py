from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProviderEndpointProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_id: str
    display_name: str
    api_style: str = "openai-compatible"
    base_url: str | None = None
    api_version: str | None = None
    deployment_name: str | None = None
    organization: str | None = None
    custom_headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float | None = None
    default_model: str | None = None
    available_models: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


OPENAI_PROFILE = ProviderEndpointProfile(
    provider_id="openai",
    display_name="OpenAI",
    base_url="https://api.openai.com/v1",
)

AZURE_OPENAI_PROFILE = ProviderEndpointProfile(
    provider_id="azure-openai",
    display_name="Azure OpenAI",
    base_url=None,
    api_version=None,
    deployment_name=None,
)

AWS_MANTLE_PROFILE = ProviderEndpointProfile(
    provider_id="aws-mantle",
    display_name="AWS Mantle",
    base_url=None,
)

OPENROUTER_PROFILE = ProviderEndpointProfile(
    provider_id="openrouter",
    display_name="OpenRouter",
    base_url="https://openrouter.ai/api/v1",
)

SILICONFLOW_PROFILE = ProviderEndpointProfile(
    provider_id="siliconflow",
    display_name="SiliconFlow",
    base_url="https://api.siliconflow.cn/v1",
)

GROQ_PROFILE = ProviderEndpointProfile(
    provider_id="groq",
    display_name="Groq",
    base_url="https://api.groq.com/openai/v1",
)


BUILTIN_OPENAI_COMPATIBLE_PROFILES: tuple[ProviderEndpointProfile, ...] = (
    OPENAI_PROFILE,
    AZURE_OPENAI_PROFILE,
    AWS_MANTLE_PROFILE,
    OPENROUTER_PROFILE,
    SILICONFLOW_PROFILE,
    GROQ_PROFILE,
)
