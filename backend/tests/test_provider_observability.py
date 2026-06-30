from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.routes import provider_observability as provider_observability_route
from app.services.event_service import EventService
from app.services.provider_observability_service import (
    ProviderObservabilityGenerationError,
    ProviderObservabilityService,
)
from app.services.trace_service import TraceService


GENERATED_AT = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


class FailingEvents:
    def list_persisted_events(self):
        raise RuntimeError("event store unavailable")

    def emit_event_sync(self, **kwargs):
        return None


def append_event(
    trace: TraceService,
    event_id: int,
    event_type: EventType,
    ts: str,
    metadata: dict,
    severity: Severity = Severity.INFO,
) -> None:
    trace.append_event(
        RuntimeEvent(
            id=event_id,
            ts=ts,
            type=event_type,
            severity=severity,
            message=event_type.value,
            metadata=metadata,
        )
    )


def make_service(tmp_path) -> tuple[ProviderObservabilityService, EventService]:
    trace = TraceService(tmp_path / "providers.db")
    events = EventService(trace)
    append_event(
        trace,
        1,
        EventType.PLANNER_COMPLETED,
        "2026-06-15T10:00:00+00:00",
        {
            "provider_name": "openai",
            "model_name": "gpt-4.1",
            "success": True,
            "latency_ms": 100,
            "input_tokens": 10,
            "output_tokens": 20,
            "estimated_cost_usd": 0.03,
        },
    )
    append_event(
        trace,
        2,
        EventType.PLANNER_COMPLETED,
        "2026-06-15T10:01:00+00:00",
        {
            "provider_name": "openai",
            "model_name": "gpt-4.1",
            "status": "completed",
            "latency_ms": 200,
            "prompt_tokens": 5,
            "completion_tokens": 15,
            "cost_usd": 0.02,
        },
    )
    append_event(
        trace,
        3,
        EventType.PLANNER_COMPLETED,
        "2026-06-15T10:02:00+00:00",
        {
            "provider_name": "anthropic",
            "model_name": "claude-3.5",
            "status": "failed",
            "request_latency_ms": 300,
            "total_tokens": 50,
        },
        severity=Severity.ERROR,
    )
    append_event(
        trace,
        4,
        EventType.PLANNER_COMPLETED,
        "2026-06-15T10:03:00+00:00",
        {
            "provider": "openrouter",
            "model": "mistral-small",
            "status": "completed",
        },
    )
    append_event(
        trace,
        5,
        EventType.PLANNER_COMPLETED,
        "2026-06-15T10:04:00+00:00",
        {
            "provider_name": "openai",
            "latency_ms": 50,
        },
    )
    service = ProviderObservabilityService(
        events=events,
        clock=lambda: GENERATED_AT,
        timer=iter([1.0, 1.025, 2.0, 2.025, 3.0, 3.025]).__next__,
    )
    return service, events


def test_provider_usage_aggregation(tmp_path) -> None:
    service, events = make_service(tmp_path)

    report = service.generate()

    assert report.total_requests == 4
    assert report.provider_count == 3
    assert report.model_count == 3
    assert report.malformed_event_count == 1
    assert [item.provider_name for item in report.provider_reports] == [
        "anthropic",
        "openai",
        "openrouter",
    ]
    openai = report.provider_reports[1]
    assert openai.model_name == "gpt-4.1"
    assert openai.total_requests == 2
    assert openai.successful_requests == 2
    assert openai.failed_requests == 0
    generated = events.list_persisted_events(
        event_type="provider_observability_generated"
    )
    assert generated[-1].metadata["provider_usage_records_total"] == 4


def test_model_usage_aggregation(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    models = service.model_usage()

    assert [(item.provider_name, item.model_name) for item in models] == [
        ("anthropic", "claude-3.5"),
        ("openai", "gpt-4.1"),
        ("openrouter", "mistral-small"),
    ]
    assert models[1].estimated_total_tokens == 50
    assert models[1].estimated_cost_usd == 0.05


def test_latency_aggregation(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    latency = service.generate().latency

    assert latency[0].provider_name == "anthropic"
    assert latency[0].average_latency_ms == 300.0
    assert latency[1].provider_name == "openai"
    assert latency[1].latency_sample_count == 2
    assert latency[1].average_latency_ms == 150.0
    assert latency[1].max_latency_ms == 200.0


def test_cost_estimate_aggregation(tmp_path) -> None:
    service, events = make_service(tmp_path)

    costs = service.cost_summary()

    openai = costs[1]
    assert openai.provider_name == "openai"
    assert openai.estimated_input_tokens == 15
    assert openai.estimated_output_tokens == 35
    assert openai.estimated_total_tokens == 50
    assert openai.estimated_cost_usd == 0.05
    assert openai.cost_estimated is True
    cost_events = events.list_persisted_events(
        event_type="provider_cost_estimate_generated"
    )
    assert cost_events[-1].metadata["estimated"] is True
    assert cost_events[-1].metadata["provider_estimated_cost_total"] == 0.05


def test_missing_cost_and_token_data_is_unknown_not_failure(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    openrouter = service.generate().costs[2]

    assert openrouter.provider_name == "openrouter"
    assert openrouter.estimated_input_tokens is None
    assert openrouter.estimated_output_tokens is None
    assert openrouter.estimated_total_tokens is None
    assert openrouter.estimated_cost_usd is None
    assert openrouter.cost_estimated is False
    assert openrouter.missing_token_or_cost_records == 2


def test_provider_report_deterministic_ordering(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    first = service.generate()
    second = service.generate()

    assert first.provider_reports == second.provider_reports
    assert first.model_usage == second.model_usage
    assert first.costs == second.costs


def test_malformed_provider_metadata_is_skipped(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    report = service.generate()

    assert report.malformed_event_count == 1
    assert all(
        item.model_name != ""
        for item in report.provider_reports
    )


def test_partial_event_history_with_provider_filter(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    report = service.generate(provider_name="openai")

    assert report.provider_count == 1
    assert report.model_count == 1
    assert report.total_requests == 2
    assert report.provider_reports[0].provider_name == "openai"


def test_empty_event_store(tmp_path) -> None:
    service = ProviderObservabilityService(
        events=EventService(TraceService(tmp_path / "empty-providers.db")),
        clock=lambda: GENERATED_AT,
        timer=iter([1.0, 1.0]).__next__,
    )

    report = service.generate()

    assert report.provider_reports == []
    assert report.model_usage == []
    assert report.costs == []
    assert report.total_requests == 0
    assert report.observability_metrics["provider_usage_records_total"] == 0


def test_provider_observability_failure() -> None:
    service = ProviderObservabilityService(
        events=FailingEvents(),
        clock=lambda: GENERATED_AT,
        timer=iter([1.0, 1.0]).__next__,
    )

    with pytest.raises(ProviderObservabilityGenerationError):
        service.generate()

    assert service.observability_metrics()[
        "provider_observability_failures_total"
    ] == 1


def seed_provider_route_events() -> None:
    # Tests use the autouse temp trace store; these diagnostics are isolated.
    from app.services.event_service import event_service

    event_service.emit_event_sync(
        EventType.PLANNER_COMPLETED,
        "Provider route event",
        metadata={
            "provider_name": "openai",
            "model_name": "gpt-route",
            "success": True,
            "latency_ms": 123,
            "input_tokens": 10,
            "output_tokens": 20,
            "estimated_cost_usd": 0.01,
        },
    )


def seed_provider_execution_events() -> None:
    from app.services.event_service import event_service

    event_service.emit_event_sync(
        EventType.AGENT_LOOP_PROVIDER_COMPLETED,
        "Agent loop provider completed",
        metadata={
            "session_id": "loop-1",
            "iteration": 1,
            "status": "completed",
            "provider_id": "openai",
            "model": "gpt-4.1",
            "effective_provider_id": "openai",
            "effective_model": "gpt-4.1",
            "routing_reason": "explicit_request",
            "routing_source": "explicit_request",
            "budget_policy": {
                "classification": "balanced",
                "warnings": ["budget warning"],
                "metadata": {},
            },
        },
    )
    event_service.emit_event_sync(
        EventType.AGENT_LOOP_PROVIDER_COMPLETED,
        "Agent loop provider completed",
        metadata={
            "session_id": "loop-2",
            "iteration": 1,
            "status": "failed",
            "provider_id": "anthropic",
            "model": "claude-3.5",
            "effective_provider_id": "anthropic",
            "effective_model": "claude-3.5",
            "routing_reason": "fallback",
            "routing_source": "policy",
            "budget_policy": {
                "classification": "premium",
                "warnings": [],
                "metadata": {},
            },
        },
    )
    event_service.emit_event_sync(
        EventType.PROVIDER_EXECUTION_FAILED,
        "Provider execution failed",
        severity=Severity.ERROR,
        metadata={
            "provider_id": "openai",
            "model": "gpt-4.1",
            "status": "failed",
            "routing_reason": "explicit_request",
            "routing_source": "explicit_request",
        },
    )


def test_provider_execution_summary_counts_agent_loop_events(tmp_path) -> None:
    seed_provider_execution_events()
    service = provider_observability_route.provider_observability_service

    summary = service.execution_summary()

    assert summary.total_executions == 2
    assert summary.completed == 1
    assert summary.failed == 1
    assert summary.by_provider == {"anthropic": 1, "openai": 1}
    assert summary.by_model == {"claude-3.5": 1, "gpt-4.1": 1}
    assert summary.budget_warnings_count == 1


def test_provider_execution_recent_returns_newest_first(tmp_path) -> None:
    seed_provider_execution_events()
    service = provider_observability_route.provider_observability_service

    recent = service.recent_executions()

    assert [item.provider_id for item in recent[:2]] == [
        "anthropic",
        "openai",
    ]
    assert recent[0].status == "failed"
    assert recent[0].routing_source == "policy"
    assert recent[0].routing_reason == "fallback"
    assert recent[0].budget_policy is None or "warnings" in recent[0].budget_policy
    assert recent[0].timestamp is not None


def test_provider_execution_endpoints_do_not_call_providers(monkeypatch) -> None:
    class NoProviderCallsService:
        def __init__(self) -> None:
            self.called = False

        def execution_summary(self):
            self.called = True
            return provider_observability_route.ProviderExecutionSummary(
                total_executions=0,
                completed=0,
                failed=0,
                by_provider={},
                by_model={},
                budget_warnings_count=0,
            )

        def recent_executions(self):
            self.called = True
            return []

    stub = NoProviderCallsService()
    monkeypatch.setattr(
        provider_observability_route,
        "provider_observability_service",
        stub,
    )

    assert provider_observability_route.get_provider_execution_summary() == (
        provider_observability_route.ProviderExecutionSummary(
            total_executions=0,
            completed=0,
            failed=0,
            by_provider={},
            by_model={},
            budget_warnings_count=0,
        )
    )
    assert provider_observability_route.get_provider_execution_recent() == []
    assert stub.called is True


def test_full_provider_observability_endpoint() -> None:
    seed_provider_route_events()
    report = provider_observability_route.get_provider_observability()
    assert report.provider_reports[0].provider_name == "openai"


def test_provider_detail_endpoint() -> None:
    seed_provider_route_events()
    report = provider_observability_route.get_provider_observability_detail(
        "openai"
    )
    assert report.provider_count == 1
    assert report.provider_reports[0].model_name == "gpt-route"


def test_model_usage_endpoint() -> None:
    seed_provider_route_events()
    models = provider_observability_route.get_provider_model_usage()
    assert models[0].model_name == "gpt-route"


def test_cost_summary_endpoint() -> None:
    seed_provider_route_events()
    costs = provider_observability_route.get_provider_costs()
    assert costs[0].estimated_cost_usd == 0.01


def test_provider_execution_summary_endpoint() -> None:
    seed_provider_execution_events()
    body = provider_observability_route.get_provider_execution_summary()
    assert body.total_executions == 2
    assert body.by_provider == {"anthropic": 1, "openai": 1}


def test_provider_execution_recent_endpoint() -> None:
    seed_provider_execution_events()
    body = provider_observability_route.get_provider_execution_recent()
    assert body[0].provider_id == "anthropic"
    assert body[0].status == "failed"
