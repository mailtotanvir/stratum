from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.provider_execution import ProviderUsage


class ProviderExecutionEventBase(BaseModel):
    provider_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    execution_id: str = Field(min_length=1)
    correlation_id: str | None = Field(default=None, min_length=1)
    capability: str | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderExecutionRequestedEvent(ProviderExecutionEventBase):
    event_type: Literal["provider_execution_requested"] = (
        "provider_execution_requested"
    )


class ProviderExecutionCompletedEvent(ProviderExecutionEventBase):
    event_type: Literal["provider_execution_completed"] = (
        "provider_execution_completed"
    )
    usage: ProviderUsage | None = None
    result_metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderExecutionFailedEvent(ProviderExecutionEventBase):
    event_type: Literal["provider_execution_failed"] = (
        "provider_execution_failed"
    )
    error_type: str = Field(min_length=1)
    error_message: str = Field(min_length=1)


class ProviderExecutionCancelledEvent(ProviderExecutionEventBase):
    event_type: Literal["provider_execution_cancelled"] = (
        "provider_execution_cancelled"
    )
    reason: str = Field(min_length=1)


class ProviderExecutionStreamEventBase(ProviderExecutionEventBase):
    sequence: int = Field(default=0, ge=0)


class ProviderExecutionStreamStartedEvent(
    ProviderExecutionStreamEventBase
):
    event_type: Literal["provider_execution_stream_started"] = (
        "provider_execution_stream_started"
    )


class ProviderExecutionStreamDeltaEvent(ProviderExecutionStreamEventBase):
    event_type: Literal["provider_execution_stream_delta"] = (
        "provider_execution_stream_delta"
    )
    content: str | None = None


class ProviderExecutionStreamCompletedEvent(
    ProviderExecutionStreamEventBase
):
    event_type: Literal["provider_execution_stream_completed"] = (
        "provider_execution_stream_completed"
    )
    usage: ProviderUsage | None = None


class ProviderExecutionStreamFailedEvent(
    ProviderExecutionStreamEventBase
):
    event_type: Literal["provider_execution_stream_failed"] = (
        "provider_execution_stream_failed"
    )
    error_type: str = Field(min_length=1)
    error_message: str = Field(min_length=1)
