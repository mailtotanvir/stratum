from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.decision_trail import DecisionTrail
from app.models.proposal import ProposalSourceType
from app.models.runtime_query import RuntimeQuery
from app.query.runtime_query_handler import RuntimeQueryHandler
from app.query.runtime_query_registry import (
    RuntimeQueryAlreadyRegisteredError,
    RuntimeQueryNotFoundError,
    RuntimeQueryRegistry,
    runtime_query_registry,
)
from app.query.session_decision_summary_query import (
    SESSION_DECISION_SUMMARY_QUERY_NAME,
    SessionDecisionSummaryQuery,
)
from app.services.event_service import EventService, event_service
from app.services.runtime_query_execution_service import (
    RuntimeQueryExecutionService,
)
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


class ExampleQueryHandler:
    def metadata(self) -> RuntimeQuery:
        return RuntimeQuery(
            query_name="example_query",
            query_version=2,
            description="Example read-only runtime query.",
            query_type="diagnostic_query",
            supported_parameters={
                "value": {"type": "string", "required": False}
            },
            result_schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
            },
        )

    def execute(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return {"value": parameters.get("value", "default")}


def make_registry(tmp_path) -> tuple[RuntimeQueryRegistry, EventService]:
    events = EventService(TraceService(tmp_path / "runtime_queries.db"))
    registry = RuntimeQueryRegistry(
        events=events,
        clock=lambda: datetime(2026, 6, 11, 14, 0, tzinfo=UTC),
    )
    return registry, events


def test_runtime_query_registration_and_lookup(tmp_path) -> None:
    registry, events = make_registry(tmp_path)
    handler = ExampleQueryHandler()

    registry.register(handler)

    assert isinstance(handler, RuntimeQueryHandler)
    assert registry.get("example_query") is handler
    assert [
        event.type.value for event in events.list_persisted_events()
    ] == ["runtime_query_registered"]
    assert events.list_persisted_events()[0].metadata == {
        "query_name": "example_query",
        "query_version": 2,
        "handler": "ExampleQueryHandler",
    }


def test_runtime_query_discovery_is_sorted_and_does_not_execute(
    tmp_path,
) -> None:
    registry, events = make_registry(tmp_path)
    first = ExampleQueryHandler()

    class AlphaQueryHandler(ExampleQueryHandler):
        def metadata(self) -> RuntimeQuery:
            return super().metadata().model_copy(
                update={"query_name": "alpha_query"}
            )

        def execute(self, parameters: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("discovery must not execute queries")

    registry.register(first)
    registry.register(AlphaQueryHandler())

    queries = registry.list_queries()

    assert [query.query_name for query in queries] == [
        "alpha_query",
        "example_query",
    ]
    discovered = events.list_persisted_events(
        event_type="runtime_query_discovered"
    )
    assert [event.metadata["query_name"] for event in discovered] == [
        "alpha_query",
        "example_query",
    ]


def test_runtime_query_names_must_be_unique(tmp_path) -> None:
    registry, _ = make_registry(tmp_path)
    registry.register(ExampleQueryHandler())

    with pytest.raises(
        RuntimeQueryAlreadyRegisteredError,
        match="Runtime query already registered: example_query",
    ):
        registry.register(ExampleQueryHandler())


def test_unknown_runtime_query_lookup_is_clean(tmp_path) -> None:
    registry, _ = make_registry(tmp_path)

    with pytest.raises(
        RuntimeQueryNotFoundError,
        match="Runtime query not found: missing_query",
    ):
        registry.get("missing_query")


def test_session_decision_summary_composes_existing_derived_state() -> None:
    session = SimpleNamespace(id="session-1")
    decision = SimpleNamespace(
        decision_id="decision-1",
        selected_entity_id="recommendation-1",
    )
    recommendation = SimpleNamespace(
        id="recommendation-1",
        status="promoted",
        objective="Inspect runtime state",
    )
    trail = DecisionTrail(
        proposal_id="proposal-1",
        recommendation_id=recommendation.id,
        decision_id=decision.decision_id,
        evidence_ids=["evidence-1", "evidence-2"],
        source_type=ProposalSourceType.PLANNER_RECOMMENDATION,
        created_at="2026-06-11T12:00:00Z",
    )
    handler = SessionDecisionSummaryQuery(
        sessions=SimpleNamespace(get_session=lambda session_id: session),
        decisions=SimpleNamespace(
            list_decision_records=lambda session_id: [decision]
        ),
        recommendations=SimpleNamespace(
            list_recommendations=lambda session_id: [recommendation]
        ),
        trails=SimpleNamespace(reconstruct_all=lambda: [trail]),
    )

    result = handler.execute({"session_id": session.id})

    assert result == {
        "session_id": session.id,
        "decision_count": 1,
        "selected_recommendations": [
            {
                "decision_id": decision.decision_id,
                "recommendation_id": recommendation.id,
                "status": "promoted",
                "objective": "Inspect runtime state",
            }
        ],
        "decision_trail_summary": {
            "trail_count": 1,
            "decision_ids": ["decision-1"],
            "evidence_count": 2,
            "trails": [trail.model_dump(mode="json")],
        },
    }


def test_global_runtime_query_registry_contains_example_query() -> None:
    assert runtime_query_registry.get(
        SESSION_DECISION_SUMMARY_QUERY_NAME
    ).metadata().query_name == SESSION_DECISION_SUMMARY_QUERY_NAME


def test_query_discovery_and_detail_endpoints() -> None:
    client = TestClient(app)

    discovery = client.get("/queries")
    detail = client.get(
        f"/queries/{SESSION_DECISION_SUMMARY_QUERY_NAME}"
    )

    assert discovery.status_code == 200
    assert [
        query["query_name"] for query in discovery.json()["queries"]
    ] == [SESSION_DECISION_SUMMARY_QUERY_NAME]
    assert detail.status_code == 200
    assert detail.json()["query_name"] == SESSION_DECISION_SUMMARY_QUERY_NAME
    assert detail.json()["supported_parameters"]["session_id"]["required"] is True
    assert "result_schema" in detail.json()
    discovered = event_service.list_persisted_events(
        event_type="runtime_query_discovered"
    )
    assert len(discovered) == 2


def test_query_execution_endpoint_returns_common_result_envelope() -> None:
    session = runtime_session_service.create_session(
        "runtime-query-endpoint-task"
    )

    response = TestClient(app).post(
        f"/queries/{SESSION_DECISION_SUMMARY_QUERY_NAME}/execute",
        json={"parameters": {"session_id": session.id}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query_name"] == SESSION_DECISION_SUMMARY_QUERY_NAME
    assert body["result"] == {
        "session_id": session.id,
        "decision_count": 0,
        "selected_recommendations": [],
        "decision_trail_summary": {
            "trail_count": 0,
            "decision_ids": [],
            "evidence_count": 0,
            "trails": [],
        },
    }
    assert body["success"] is True
    assert [
        diagnostic["event_type"] for diagnostic in body["diagnostics"]
    ] == [
        "runtime_query_execution_started",
        "runtime_query_execution_completed",
    ]
    assert body["execution_metadata"]["query_version"] == 1
    assert body["execution_metadata"]["handler_name"] == (
        "SessionDecisionSummaryQuery"
    )
    executed = event_service.list_persisted_events(
        event_type="runtime_query_executed"
    )
    assert len(executed) == 1
    assert executed[0].metadata == {
        "query_name": SESSION_DECISION_SUMMARY_QUERY_NAME,
        "query_version": 1,
        "handler": "SessionDecisionSummaryQuery",
    }


def test_query_endpoints_return_unknown_query_errors() -> None:
    client = TestClient(app)

    detail = client.get("/queries/missing_query")
    execution = client.post(
        "/queries/missing_query/execute",
        json={"parameters": {}},
    )

    assert detail.status_code == 404
    assert execution.status_code == 404
    assert detail.json() == {
        "detail": "Runtime query not found: missing_query"
    }
    assert execution.json() == detail.json()
