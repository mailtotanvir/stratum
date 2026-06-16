from datetime import datetime

from pydantic import BaseModel, Field


class ProviderUsageSummary(BaseModel):
    provider_name: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    total_requests: int = Field(ge=0)
    successful_requests: int = Field(ge=0)
    failed_requests: int = Field(ge=0)
    average_latency_ms: float | None = Field(default=None, ge=0)
    max_latency_ms: float | None = Field(default=None, ge=0)
    estimated_input_tokens: int | None = Field(default=None, ge=0)
    estimated_output_tokens: int | None = Field(default=None, ge=0)
    estimated_total_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    last_used_at: datetime | None = None


class ModelUsageSummary(BaseModel):
    provider_name: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    total_requests: int = Field(ge=0)
    successful_requests: int = Field(ge=0)
    failed_requests: int = Field(ge=0)
    estimated_total_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    last_used_at: datetime | None = None


class ProviderLatencySummary(BaseModel):
    provider_name: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    latency_sample_count: int = Field(ge=0)
    average_latency_ms: float | None = Field(default=None, ge=0)
    max_latency_ms: float | None = Field(default=None, ge=0)


class ProviderCostSummary(BaseModel):
    provider_name: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    estimated_input_tokens: int | None = Field(default=None, ge=0)
    estimated_output_tokens: int | None = Field(default=None, ge=0)
    estimated_total_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    cost_estimated: bool
    missing_token_or_cost_records: int = Field(ge=0)


class ProviderObservabilityReport(BaseModel):
    generated_at: datetime
    provider_reports: list[ProviderUsageSummary]
    model_usage: list[ModelUsageSummary]
    latency: list[ProviderLatencySummary]
    costs: list[ProviderCostSummary]
    provider_count: int = Field(ge=0)
    model_count: int = Field(ge=0)
    total_requests: int = Field(ge=0)
    malformed_event_count: int = Field(ge=0)
    estimated: bool = True
    metadata: dict[str, object] = Field(default_factory=dict)
    observability_metrics: dict[str, float | int] = Field(default_factory=dict)
