from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from app.models.provider_observability import (
    ModelUsageSummary,
    ProviderCostSummary,
    ProviderLatencySummary,
    ProviderObservabilityReport,
    ProviderUsageSummary,
)
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.services.event_service import EventService, event_service


PROVIDER_OBSERVABILITY_EVENT_TYPES = frozenset(
    {
        EventType.PROVIDER_OBSERVABILITY_GENERATED.value,
        EventType.PROVIDER_OBSERVABILITY_FAILED.value,
        EventType.PROVIDER_COST_ESTIMATE_GENERATED.value,
    }
)
PROVIDER_NAME_FIELDS = ("provider_name", "provider", "llm_provider")
MODEL_NAME_FIELDS = ("model_name", "model", "llm_model")
LATENCY_FIELDS = (
    "latency_ms",
    "duration_ms",
    "request_latency_ms",
    "execution_duration_ms",
)
INPUT_TOKEN_FIELDS = ("input_tokens", "prompt_tokens", "estimated_input_tokens")
OUTPUT_TOKEN_FIELDS = (
    "output_tokens",
    "completion_tokens",
    "estimated_output_tokens",
)
TOTAL_TOKEN_FIELDS = ("total_tokens", "estimated_total_tokens")
COST_FIELDS = ("estimated_cost_usd", "cost_usd")


class ProviderObservabilityGenerationError(RuntimeError):
    pass


@dataclass
class ProviderUsageAccumulator:
    provider_name: str
    model_name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    latencies: list[float] = field(default_factory=list)
    estimated_input_tokens: int | None = None
    estimated_output_tokens: int | None = None
    estimated_total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    missing_token_or_cost_records: int = 0
    last_used_at: datetime | None = None


class ProviderObservabilityService:
    def __init__(
        self,
        events: EventService | None = None,
        clock: Callable[[], datetime] | None = None,
        timer: Callable[[], float] | None = None,
    ) -> None:
        self._events = events or event_service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._timer = timer or perf_counter
        self._requests_total = 0
        self._failures_total = 0
        self._usage_records_total = 0
        self._estimated_cost_total = 0.0

    def generate(
        self,
        provider_name: str | None = None,
    ) -> ProviderObservabilityReport:
        started_at = self._timer()
        self._requests_total += 1
        try:
            report = self._generate(provider_name=provider_name)
        except Exception as exc:
            self._failures_total += 1
            self._events.emit_event_sync(
                event_type=EventType.PROVIDER_OBSERVABILITY_FAILED,
                severity=Severity.ERROR,
                message=f"Provider observability generation failed: {exc}",
                metadata={
                    "provider_name": provider_name,
                    "error_type": type(exc).__name__,
                    "generation_duration_ms": self._duration_ms(started_at),
                    **self.observability_metrics(),
                },
            )
            raise ProviderObservabilityGenerationError(
                f"Provider observability generation failed: {exc}"
            ) from exc

        self._usage_records_total = report.total_requests
        self._estimated_cost_total = round(
            sum(
                item.estimated_cost_usd or 0.0
                for item in report.costs
            ),
            6,
        )
        report.observability_metrics = self.observability_metrics()
        self._events.emit_event_sync(
            event_type=EventType.PROVIDER_OBSERVABILITY_GENERATED,
            message="Provider observability generated",
            metadata={
                "provider_name": provider_name,
                "generation_duration_ms": self._duration_ms(started_at),
                **self.observability_metrics(),
            },
        )
        self._events.emit_event_sync(
            event_type=EventType.PROVIDER_COST_ESTIMATE_GENERATED,
            message="Provider cost estimate generated",
            metadata={
                "provider_name": provider_name,
                "estimated": True,
                "estimated_cost_usd": self._estimated_cost_total,
                **self.observability_metrics(),
            },
        )
        return report

    def model_usage(self) -> list[ModelUsageSummary]:
        return self.generate().model_usage

    def cost_summary(self) -> list[ProviderCostSummary]:
        return self.generate().costs

    def observability_metrics(self) -> dict[str, float | int]:
        return {
            "provider_observability_requests_total": self._requests_total,
            "provider_observability_failures_total": self._failures_total,
            "provider_usage_records_total": self._usage_records_total,
            "provider_estimated_cost_total": self._estimated_cost_total,
        }

    def _generate(
        self,
        provider_name: str | None,
    ) -> ProviderObservabilityReport:
        accumulators: dict[
            tuple[str, str],
            ProviderUsageAccumulator,
        ] = {}
        malformed_event_count = 0
        for event in self._source_events():
            provider = _string_field(event.metadata, PROVIDER_NAME_FIELDS)
            model = _string_field(event.metadata, MODEL_NAME_FIELDS)
            if provider is None and model is None:
                continue
            if provider is None or model is None:
                malformed_event_count += 1
                continue
            if provider_name is not None and provider != provider_name:
                continue
            key = (provider, model)
            usage = accumulators.setdefault(
                key,
                ProviderUsageAccumulator(
                    provider_name=provider,
                    model_name=model,
                ),
            )
            self._apply_event(usage, event)

        ordered = [
            accumulators[key]
            for key in sorted(accumulators)
        ]
        provider_reports = [self._usage_summary(item) for item in ordered]
        costs = [self._cost_summary(item) for item in ordered]
        return ProviderObservabilityReport(
            generated_at=self._clock(),
            provider_reports=provider_reports,
            model_usage=[self._model_summary(item) for item in ordered],
            latency=[self._latency_summary(item) for item in ordered],
            costs=costs,
            provider_count=len({item.provider_name for item in ordered}),
            model_count=len(ordered),
            total_requests=sum(item.total_requests for item in ordered),
            malformed_event_count=malformed_event_count,
            metadata={
                "derived": True,
                "authoritative_source": "runtime_event_store",
                "estimated_costs": True,
                "external_billing_api_called": False,
                "provider_routing_changed": False,
            },
            observability_metrics=self.observability_metrics(),
        )

    def _apply_event(
        self,
        usage: ProviderUsageAccumulator,
        event: RuntimeEvent,
    ) -> None:
        usage.total_requests += 1
        status = _request_status(event)
        if status == "success":
            usage.successful_requests += 1
        elif status == "failure":
            usage.failed_requests += 1

        latency = _number_field(event.metadata, LATENCY_FIELDS)
        if latency is not None and latency >= 0:
            usage.latencies.append(latency)

        input_tokens = _int_field(event.metadata, INPUT_TOKEN_FIELDS)
        output_tokens = _int_field(event.metadata, OUTPUT_TOKEN_FIELDS)
        total_tokens = _int_field(event.metadata, TOTAL_TOKEN_FIELDS)
        if total_tokens is None and (
            input_tokens is not None or output_tokens is not None
        ):
            total_tokens = (input_tokens or 0) + (output_tokens or 0)
        cost = _number_field(event.metadata, COST_FIELDS)

        if input_tokens is None and output_tokens is None and total_tokens is None:
            usage.missing_token_or_cost_records += 1
        else:
            usage.estimated_input_tokens = _add_optional_int(
                usage.estimated_input_tokens,
                input_tokens,
            )
            usage.estimated_output_tokens = _add_optional_int(
                usage.estimated_output_tokens,
                output_tokens,
            )
            usage.estimated_total_tokens = _add_optional_int(
                usage.estimated_total_tokens,
                total_tokens,
            )
        if cost is None:
            usage.missing_token_or_cost_records += 1
        else:
            usage.estimated_cost_usd = round(
                (usage.estimated_cost_usd or 0.0) + cost,
                6,
            )
        occurred_at = _event_datetime(event)
        if occurred_at is not None and (
            usage.last_used_at is None or occurred_at > usage.last_used_at
        ):
            usage.last_used_at = occurred_at

    @staticmethod
    def _usage_summary(
        usage: ProviderUsageAccumulator,
    ) -> ProviderUsageSummary:
        average_latency = _average(usage.latencies)
        return ProviderUsageSummary(
            provider_name=usage.provider_name,
            model_name=usage.model_name,
            total_requests=usage.total_requests,
            successful_requests=usage.successful_requests,
            failed_requests=usage.failed_requests,
            average_latency_ms=average_latency,
            max_latency_ms=max(usage.latencies) if usage.latencies else None,
            estimated_input_tokens=usage.estimated_input_tokens,
            estimated_output_tokens=usage.estimated_output_tokens,
            estimated_total_tokens=usage.estimated_total_tokens,
            estimated_cost_usd=usage.estimated_cost_usd,
            last_used_at=usage.last_used_at,
        )

    @staticmethod
    def _model_summary(
        usage: ProviderUsageAccumulator,
    ) -> ModelUsageSummary:
        return ModelUsageSummary(
            provider_name=usage.provider_name,
            model_name=usage.model_name,
            total_requests=usage.total_requests,
            successful_requests=usage.successful_requests,
            failed_requests=usage.failed_requests,
            estimated_total_tokens=usage.estimated_total_tokens,
            estimated_cost_usd=usage.estimated_cost_usd,
            last_used_at=usage.last_used_at,
        )

    @staticmethod
    def _latency_summary(
        usage: ProviderUsageAccumulator,
    ) -> ProviderLatencySummary:
        return ProviderLatencySummary(
            provider_name=usage.provider_name,
            model_name=usage.model_name,
            latency_sample_count=len(usage.latencies),
            average_latency_ms=_average(usage.latencies),
            max_latency_ms=max(usage.latencies) if usage.latencies else None,
        )

    @staticmethod
    def _cost_summary(
        usage: ProviderUsageAccumulator,
    ) -> ProviderCostSummary:
        return ProviderCostSummary(
            provider_name=usage.provider_name,
            model_name=usage.model_name,
            estimated_input_tokens=usage.estimated_input_tokens,
            estimated_output_tokens=usage.estimated_output_tokens,
            estimated_total_tokens=usage.estimated_total_tokens,
            estimated_cost_usd=usage.estimated_cost_usd,
            cost_estimated=(
                usage.estimated_input_tokens is not None
                or usage.estimated_output_tokens is not None
                or usage.estimated_total_tokens is not None
                or usage.estimated_cost_usd is not None
            ),
            missing_token_or_cost_records=(
                usage.missing_token_or_cost_records
            ),
        )

    def _source_events(self) -> list[RuntimeEvent]:
        return [
            event
            for event in self._events.list_persisted_events()
            if event.type.value not in PROVIDER_OBSERVABILITY_EVENT_TYPES
        ]

    def _duration_ms(self, started_at: float) -> float:
        return round(max(0.0, (self._timer() - started_at) * 1000), 3)


def _string_field(
    metadata: dict[str, Any],
    fields: tuple[str, ...],
) -> str | None:
    for field in fields:
        value = metadata.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def _number_field(
    metadata: dict[str, Any],
    fields: tuple[str, ...],
) -> float | None:
    for field in fields:
        value = metadata.get(field)
        if isinstance(value, int | float) and value >= 0:
            return float(value)
    return None


def _int_field(
    metadata: dict[str, Any],
    fields: tuple[str, ...],
) -> int | None:
    for field in fields:
        value = metadata.get(field)
        if isinstance(value, int) and value >= 0:
            return value
    return None


def _add_optional_int(current: int | None, value: int | None) -> int | None:
    if value is None:
        return current
    return (current or 0) + value


def _request_status(event: RuntimeEvent) -> str | None:
    value = event.metadata.get("success")
    if value is True:
        return "success"
    if value is False:
        return "failure"
    status = event.metadata.get("status")
    if isinstance(status, str):
        normalized = status.lower()
        if normalized in {"success", "succeeded", "completed", "ok"}:
            return "success"
        if normalized in {"failure", "failed", "error", "errored"}:
            return "failure"
    if event.type.value.endswith("_completed"):
        return "success"
    if event.type.value.endswith("_failed") or event.severity in {
        Severity.ERROR,
        Severity.CRITICAL,
    }:
        return "failure"
    return None


def _event_datetime(event: RuntimeEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(event.ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


provider_observability_service = ProviderObservabilityService()
