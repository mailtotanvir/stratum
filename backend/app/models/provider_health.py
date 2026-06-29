from pydantic import BaseModel, ConfigDict


class ProviderHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_id: str | None = None
    ready: bool = False
    configured: bool = False
    enabled: bool = False

    transport: str = "httpx"
    protocol: str = "openai-compatible"

    supports_completion: bool = False
    supports_streaming: bool = False

    status: str = "unconfigured"
