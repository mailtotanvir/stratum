from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class ProviderConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("provider_id", "provider_name"),
    )
    display_name: str = Field(min_length=1)
    api_style: str = Field(default="provider_adapter", min_length=1)
    base_url: str | None = None
    supports_streaming: bool = False
    supports_tools: bool = False
    supports_json_mode: bool = False
    supports_reasoning: bool = False
    supports_vision: bool = False
    supports_embeddings: bool = False
    supports_audio: bool = False
    default_model: str | None = None
    available_models: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    enabled: bool = Field(default=False, exclude=True)
    timeout_seconds: float = Field(default=120, gt=0, exclude=True)
    default_headers: dict[str, str] = Field(
        default_factory=dict,
        exclude=True,
    )

    @property
    def provider_name(self) -> str:
        return self.provider_id

    @field_validator("provider_id", "display_name", "api_style")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("base_url")
    @classmethod
    def validate_optional_base_url(
        cls,
        value: str | None,
    ) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be empty")
        return value


class OpenAICompatibleProviderConfiguration(ProviderConfiguration):
    pass


class ProviderConfigurationSnapshot(BaseModel):
    providers: list[ProviderConfiguration] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
