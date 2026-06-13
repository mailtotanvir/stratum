from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_query import RuntimeQuery
from app.models.runtime_query_execution import RuntimeQueryExecutionMetadata
from app.query.runtime_query_registry import RuntimeQueryRegistry
from app.query.session_decision_summary_query import (
    SESSION_DECISION_SUMMARY_QUERY_NAME,
)
from app.services.event_service import EventService, event_service
from app.services.query_history_service import (
    QueryExecutionRecordNotFoundError,
    QueryHistoryService,
)
from app.services.query_lineage_service import QueryLineageService
from app.services.query_verification_service import (
    QueryVerificationService,
)
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


EXECUTED_AT = datetime(2026, 6, 13, 17, 0, tzinfo=UTC)


class LineageQueryHandler:
    def __init__(self) -> None:
        self.execute_count = 0

    def metadata(self) -> RuntimeQuery:
        return RuntimeQuery(
            query_name="lineage_query",
            query_version=4,
            description="Inspect generic session lineage.",
            query_type="session_query",
            supported_parameters={
                "session_id": {"type": "string", "required": True}
            },
            result_schema={"type": "object"},
        )

    def execute(self, parameters: dict[str, Any]) -> dict[str, Any]:
        self.execute_count += 1
        return {"session_id": parameters["session_id"], "count": 2}


def make_lineage_service(tmp_path):
    events = EventService(TraceService(tmp_path / "query_lineage.db"))
    history = QueryHistoryService(events)
    registry = RuntimeQueryRegistry(
        events=events,
        emit_registration_diagnostics=False,
    )
    handler = LineageQueryHandler()
    registry.register(handler)
    service = QueryLineageService(
        registry=registry,
        history=history,
        events=events,
    )
    return service, history, registry, handler, events


def record_execution(history: QueryHistoryService) -> None:
    history.record_execution(
        execution_id="execution-1",
        executed_at=EXECUTED_AT,
        parameters={"session_id": "session-1"},
        execution_metadata=RuntimeQueryExecutionMetadata(
            query_name="lineage_query",
            query_version=4,
            handler_name="LineageQueryHandler",
            execution_duration_ms=6.0,
        ),
        success=True,
        result_summary={"session_id": "session-1", "count": 2},
    )


def emit_sources(events: EventService) -> None:
    events.emit_event_sync(
        event_type="planner_completed",
        message="Planner source",
        metadata={
            "session_id": "session-1",
            "recommendation_id": "recommendation-1",
        },
    )
    events.emit_event_sync(
        event_type="decision_record_created",
        message="Decision source",
        metadata={
            "session_id": "session-1",
            "decision_id": "decision-1",
        },
    )


def test_query_lineage_is_registry_driven_and_deterministic(
    tmp_path,
) -> None:
    service, history, _, handler, events = make_lineage_service(tmp_path)
    record_execution(history)
    emit_sources(events)

    first = service.generate("execution-1")
    second = service.generate("execution-1")

    assert first == second
    assert handler.execute_count == 0
    assert first.model_dump(mode="json") == {
        "execution_id": "execution-1",
        "query_name": "lineage_query",
        "query_version": 4,
        "handler_name": "LineageQueryHandler",
        "generated_at": "2026-06-13T17:00:00Z",
        "source_types": [
            "decision_record",
            "planner",
            "runtime_event",
            "runtime_session",
        ],
        "source_identifiers": {
            "decision_ids": ["decision-1"],
            "event_ids": [3, 4],
            "recommendation_ids": ["recommendation-1"],
            "session_id": "session-1",
        },
        "source_counts": {
            "decision_record": 1,
            "planner": 1,
            "runtime_event": 2,
            "runtime_session": 1,
        },
        "reconstruction_info": {
            "query_name": "lineage_query",
            "query_version": 4,
            "handler_name": "LineageQueryHandler",
            "execution_timestamp": "2026-06-13T17:00:00Z",
            "parameter_snapshot": {"session_id": "session-1"},
            "reconstruction_version": 1,
        },
        "lineage_version": 1,
    }
    generated = events.list_persisted_events(
        event_type="query_lineage_generated"
    )
    assert len(generated) == 2
    assert generated[0].metadata == {
        "execution_id": "execution-1",
        "query_name": "lineage_query",
        "query_version": 4,
        "source_count": 3,
    }


def test_query_lineage_unknown_execution_emits_failure(
    tmp_path,
) -> None:
    service, _, _, _, events = make_lineage_service(tmp_path)

    with pytest.raises(
        QueryExecutionRecordNotFoundError,
        match="Query execution record not found: missing-execution",
    ):
        service.generate("missing-execution")

    failed = events.list_persisted_events(
        event_type="query_lineage_generation_failed"
    )
    assert failed[-1].severity.value == "error"
    assert failed[-1].metadata == {
        "execution_id": "missing-execution",
        "query_name": None,
        "query_version": None,
        "source_count": 0,
    }


def test_query_history_record_exposes_lineage_reference(tmp_path) -> None:
    _, history, _, _, events = make_lineage_service(tmp_path)
    record_execution(history)

    record = history.load_execution_record("execution-1")

    assert record.lineage_reference == {
        "execution_id": "execution-1",
        "endpoint": "/queries/history/execution-1/lineage",
    }
    assert len(
        events.list_persisted_events(
            event_type="query_history_recorded"
        )
    ) == 1


def test_query_verification_includes_lineage_when_available(
    tmp_path,
) -> None:
    (
        lineage,
        history,
        registry,
        handler,
        events,
    ) = make_lineage_service(tmp_path)
    record_execution(history)
    emit_sources(events)
    history_before = deepcopy(
        events.list_persisted_events(
            event_type="query_history_recorded"
        )
    )
    verification = QueryVerificationService(
        registry=registry,
        history=history,
        events=events,
        lineage=lineage,
        clock=lambda: EXECUTED_AT,
    )

    result = verification.verify("execution-1")

    assert result.verified is True
    assert result.lineage is not None
    assert result.lineage.source_identifiers["decision_ids"] == [
        "decision-1"
    ]
    assert result.lineage.reconstruction_info.parameter_snapshot == {
        "session_id": "session-1"
    }
    assert handler.execute_count == 1
    assert events.list_persisted_events(
        event_type="query_history_recorded"
    ) == history_before


def test_query_lineage_endpoint_is_operational() -> None:
    session = runtime_session_service.create_session(
        "query-lineage-endpoint-task"
    )
    event_service.emit_event_sync(
        event_type="decision_record_created",
        message="Query lineage endpoint source",
        metadata={
            "session_id": session.id,
            "decision_id": "endpoint-decision",
        },
    )
    client = TestClient(app)
    execution = client.post(
        f"/queries/{SESSION_DECISION_SUMMARY_QUERY_NAME}/execute",
        json={"parameters": {"session_id": session.id}},
    )
    execution_id = execution.json()["execution_id"]

    response = client.get(
        f"/queries/history/{execution_id}/lineage"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["execution_id"] == execution_id
    assert body["query_name"] == SESSION_DECISION_SUMMARY_QUERY_NAME
    assert body["handler_name"] == "SessionDecisionSummaryQuery"
    assert body["source_identifiers"]["session_id"] == session.id
    assert body["source_identifiers"]["decision_ids"] == [
        "endpoint-decision"
    ]
    assert body["reconstruction_info"]["parameter_snapshot"] == {
        "session_id": session.id
    }


def test_query_lineage_endpoint_returns_unknown_execution() -> None:
    response = TestClient(app).get(
        "/queries/history/missing-execution/lineage"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": (
            "Query execution record not found: missing-execution"
        )
    }
