from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProviderLiveVerification(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_id: str | None = None
    model: str | None = None
    status: str
    reachable: bool = False
    latency_ms: int | None = None
    http_status: int | None = None
    content_preview: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    verified_at: datetime
    metadata: dict = Field(default_factory=dict)
