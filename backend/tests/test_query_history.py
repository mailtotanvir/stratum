from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_query import RuntimeQuery
from app.models.runtime_query_execution import (
    RuntimeQueryExecutionMetadata,
    RuntimeQueryExecutionRequest,
)
from app.query.runtime_query_registry import RuntimeQueryRegistry
from app.query.session_decision_summary_query import (
    SESSION_DECISION_SUMMARY_QUERY_NAME,
)
from app.services.event_service import EventService
from app.services.query_history_service import (
    QueryExecutionRecordNotFoundError,
    QueryHistoryService,
)
from app.services.runtime_query_execution_service import (
    RuntimeQueryExecutionService,
)
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


EXECUTED_AT = datetime(2026, 6, 13, 15, 30, tzinfo=UTC)


def make_history(tmp_path) -> tuple[QueryHistoryService, EventService]:
    events = EventService(TraceService(tmp_path / "query_history.db"))
    return QueryHistoryService(events), events


def record_execution(history: QueryHistoryService):
    return history.record_execution(
        execution_id="execution-1",
        executed_at=EXECUTED_AT,
        parameters={"limit": 2, "session_id": "session-1"},
        execution_metadata=RuntimeQueryExecutionMetadata(
            query_name="session_summary",
            query_version=3,
            handler_name="SessionSummaryQuery",
            execution_duration_ms=12.5,
        ),
        success=True,
        result_summary={"count": 2},
    )


def test_query_history_creation_and_retrieval(tmp_path) -> None:
    history, events = make_history(tmp_path)

    created = record_execution(history)
    retrieved = history.retrieve_history()

    assert retrieved.execution_records == [created]
    assert retrieved.metadata.model_dump() == {
        "record_count": 1,
        "reconstruction_version": 1,
    }
    assert retrieved.reconstruction_information[0].model_dump(
        mode="json"
    ) == {
        "query_name": "session_summary",
        "query_version": 3,
        "handler_name": "SessionSummaryQuery",
        "execution_timestamp": "2026-06-13T15:30:00Z",
        "parameter_snapshot": {
            "limit": 2,
            "session_id": "session-1",
        },
        "reconstruction_version": 1,
    }
    recorded = events.list_persisted_events(
        event_type="query_history_recorded"
    )
    assert len(recorded) == 1
    assert recorded[0].metadata["execution_record"]["result_summary"] == {
        "count": 2
    }


def test_query_reconstruction_info_is_deterministic_and_snapshot_based(
    tmp_path,
) -> None:
    history, _ = make_history(tmp_path)
    record = record_execution(history)

    first = history.generate_reconstruction_info(record)
    record.parameters["limit"] = 99
    stored = history.retrieve_execution("execution-1")
    second = history.generate_reconstruction_info(
        stored.execution_record
    )

    assert first == second
    assert second.parameter_snapshot["limit"] == 2


def test_unknown_query_execution_record_is_clean(tmp_path) -> None:
    history, _ = make_history(tmp_path)

    with pytest.raises(
        QueryExecutionRecordNotFoundError,
        match="Query execution record not found: missing-execution",
    ):
        history.retrieve_execution("missing-execution")


def test_query_history_diagnostics_include_execution_identity(
    tmp_path,
) -> None:
    history, events = make_history(tmp_path)
    record_execution(history)
    history.retrieve_execution("execution-1")

    for event_type in [
        "query_history_recorded",
        "query_history_retrieved",
        "query_reconstruction_generated",
    ]:
        matching = events.list_persisted_events(event_type=event_type)
        assert matching
        assert matching[-1].metadata["execution_id"] == "execution-1"
        assert matching[-1].metadata["query_name"] == "session_summary"
        assert matching[-1].metadata["query_version"] == 3


class CountingQueryHandler:
    def __init__(self) -> None:
        self.call_count = 0

    def metadata(self) -> RuntimeQuery:
        return RuntimeQuery(
            query_name="counting_query",
            query_version=1,
            description="Count query handler invocations.",
            query_type="diagnostic_query",
            supported_parameters={},
            result_schema={"type": "object"},
        )

    def execute(self, parameters: dict[str, Any]) -> dict[str, int]:
        self.call_count += 1
        return {"call_count": self.call_count}


def test_history_retrieval_does_not_reexecute_query(tmp_path) -> None:
    events = EventService(TraceService(tmp_path / "no_reexecution.db"))
    registry = RuntimeQueryRegistry(
        events=events,
        emit_registration_diagnostics=False,
    )
    handler = CountingQueryHandler()
    registry.register(handler)
    history = QueryHistoryService(events)
    execution = RuntimeQueryExecutionService(
        registry=registry,
        events=events,
        history=history,
        clock=lambda: EXECUTED_AT,
        timer=lambda: 1.0,
        id_factory=lambda: "execution-1",
    )

    execution.execute(
        RuntimeQueryExecutionRequest(
            query_name="counting_query",
            parameters={},
            execution_context={},
            requested_at=EXECUTED_AT,
        )
    )
    history.retrieve_history()
    history.retrieve_execution("execution-1")

    assert handler.call_count == 1


def test_query_history_endpoints_return_list_detail_and_unknown() -> None:
    session = runtime_session_service.create_session(
        "query-history-endpoint-task"
    )
    client = TestClient(app)
    execution = client.post(
        f"/queries/{SESSION_DECISION_SUMMARY_QUERY_NAME}/execute",
        json={"parameters": {"session_id": session.id}},
    )
    execution_id = execution.json()["execution_id"]

    history = client.get("/queries/history")
    detail = client.get(f"/queries/history/{execution_id}")
    unknown = client.get("/queries/history/missing-execution")

    assert history.status_code == 200
    assert history.json()["metadata"]["record_count"] == 1
    assert history.json()["execution_records"][0]["execution_id"] == (
        execution_id
    )
    assert len(history.json()["reconstruction_information"]) == 1
    assert detail.status_code == 200
    assert detail.json()["execution_record"]["execution_id"] == execution_id
    assert detail.json()["reconstruction_info"]["parameter_snapshot"] == {
        "session_id": session.id
    }
    assert unknown.status_code == 404
    assert unknown.json() == {
        "detail": (
            "Query execution record not found: missing-execution"
        )
    }
