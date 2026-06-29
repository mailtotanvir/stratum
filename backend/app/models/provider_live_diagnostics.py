from pydantic import BaseModel, ConfigDict, Field


class ProviderLiveDiagnostics(BaseModel):
    model_config = ConfigDict(frozen=True)

    configured: bool = False
    ready: bool = False
    provider_id: str | None = None
    display_name: str | None = None
    api_style: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    enabled: bool = False
    supports_streaming: bool = False
    has_api_key: bool = False
    issues: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
