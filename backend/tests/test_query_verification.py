from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType
from app.models.runtime_query import RuntimeQuery
from app.models.runtime_query_execution import RuntimeQueryExecutionMetadata
from app.query.runtime_query_registry import (
    RuntimeQueryNotFoundError,
    RuntimeQueryRegistry,
)
from app.query.session_decision_summary_query import (
    SESSION_DECISION_SUMMARY_QUERY_NAME,
)
from app.services.event_service import EventService
from app.services.query_history_service import (
    QueryExecutionRecordNotFoundError,
    QueryHistoryService,
)
from app.services.query_verification_service import (
    QueryReconstructionMetadataError,
    QueryVerificationService,
    QueryVersionMismatchError,
    compare_query_results,
)
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


EXECUTED_AT = datetime(2026, 6, 13, 16, 0, tzinfo=UTC)
VERIFIED_AT = datetime(2026, 6, 13, 16, 5, tzinfo=UTC)


class MutableVerificationQuery:
    def __init__(
        self,
        result: Any,
        *,
        version: int = 1,
    ) -> None:
        self.result = result
        self.version = version
        self.calls: list[dict[str, Any]] = []

    def metadata(self) -> RuntimeQuery:
        return RuntimeQuery(
            query_name="verification_query",
            query_version=self.version,
            description="Return controlled verification data.",
            query_type="diagnostic_query",
            supported_parameters={
                "scope": {"type": "string", "required": True}
            },
            result_schema={"type": "object"},
        )

    def execute(self, parameters: dict[str, Any]) -> Any:
        self.calls.append(parameters)
        return deepcopy(self.result)


def make_verification_service(
    tmp_path,
    handler: MutableVerificationQuery | None,
) -> tuple[
    QueryVerificationService,
    QueryHistoryService,
    EventService,
]:
    events = EventService(TraceService(tmp_path / "query_verification.db"))
    history = QueryHistoryService(events)
    registry = RuntimeQueryRegistry(
        events=events,
        emit_registration_diagnostics=False,
    )
    if handler is not None:
        registry.register(handler)
    service = QueryVerificationService(
        registry=registry,
        history=history,
        events=events,
        clock=lambda: VERIFIED_AT,
    )
    return service, history, events


def record_history(
    history: QueryHistoryService,
    *,
    result_summary: Any,
    version: int = 1,
) -> None:
    history.record_execution(
        execution_id="execution-1",
        executed_at=EXECUTED_AT,
        parameters={"scope": "session-1"},
        execution_metadata=RuntimeQueryExecutionMetadata(
            query_name="verification_query",
            query_version=version,
            handler_name="MutableVerificationQuery",
            execution_duration_ms=4.0,
        ),
        success=True,
        result_summary=result_summary,
    )


def test_query_verification_succeeds_without_mutating_history(
    tmp_path,
) -> None:
    handler = MutableVerificationQuery({"count": 2})
    service, history, events = make_verification_service(
        tmp_path,
        handler,
    )
    record_history(history, result_summary={"count": 2})
    history_events_before = deepcopy(
        events.list_persisted_events(
            event_type="query_history_recorded"
        )
    )

    result = service.verify("execution-1")

    assert result.verified is True
    assert result.verified_at == VERIFIED_AT
    assert result.original_result_summary == {"count": 2}
    assert result.rebuilt_result_summary == {"count": 2}
    assert result.differences == []
    assert result.lineage is not None
    assert result.lineage.execution_id == "execution-1"
    assert result.current_manifest is not None
    assert result.rebuilt_manifest is not None
    assert result.hash_match is True
    assert result.current_manifest.content_hash == (
        result.rebuilt_manifest.content_hash
    )
    assert handler.calls == [{"scope": "session-1"}]
    assert events.list_persisted_events(
        event_type="query_history_recorded"
    ) == history_events_before
    assert [
        diagnostic.event_type for diagnostic in result.diagnostics
    ] == [
        "query_verification_started",
        "query_verification_completed",
    ]


def test_query_verification_detects_result_drift(tmp_path) -> None:
    handler = MutableVerificationQuery(
        {
            "alpha": 2,
            "items": [{"kept": True, "unexpected": "new"}],
        }
    )
    service, history, _ = make_verification_service(tmp_path, handler)
    record_history(
        history,
        result_summary={
            "alpha": 1,
            "items": [{"kept": True}, {"missing": "old"}],
        },
    )

    result = service.verify("execution-1")

    assert result.verified is False
    assert [difference.model_dump() for difference in result.differences] == [
        {
            "field_path": "$.alpha",
            "expected_value": 1,
            "actual_value": 2,
            "difference_type": "value_mismatch",
        },
        {
            "field_path": "$.items[0].unexpected",
            "expected_value": None,
            "actual_value": "new",
            "difference_type": "unexpected_field",
        },
        {
            "field_path": "$.items[1]",
            "expected_value": {"missing": "old"},
            "actual_value": None,
            "difference_type": "missing_field",
        },
    ]
    assert result.diagnostics[-1].verified is False
    assert result.diagnostics[-1].difference_count == 3
    assert result.current_manifest is not None
    assert result.rebuilt_manifest is not None
    assert result.hash_match is False
    assert result.current_manifest.parameter_hash == (
        result.rebuilt_manifest.parameter_hash
    )
    assert result.current_manifest.result_hash != (
        result.rebuilt_manifest.result_hash
    )


def test_query_difference_generation_is_deterministic() -> None:
    expected = {"z": 1, "a": [{"value": "old"}]}
    actual = {"a": [{"value": "new"}, "extra"], "b": True}

    first = compare_query_results(expected, actual)
    second = compare_query_results(expected, actual)

    assert first == second
    assert [difference.field_path for difference in first] == [
        "$.a[0].value",
        "$.a[1]",
        "$.b",
        "$.z",
    ]
    scalar = compare_query_results("old", "new")
    assert scalar[0].difference_type == "result_summary_mismatch"


def test_query_verification_unknown_execution_id(tmp_path) -> None:
    service, _, events = make_verification_service(
        tmp_path,
        MutableVerificationQuery({}),
    )

    with pytest.raises(
        QueryExecutionRecordNotFoundError,
        match="Query execution record not found: missing-execution",
    ):
        service.verify("missing-execution")

    failed = events.list_persisted_events(
        event_type="query_verification_failed"
    )
    assert failed[-1].metadata == {
        "execution_id": "missing-execution",
        "query_name": None,
        "query_version": None,
        "verified": False,
        "difference_count": 0,
    }


def test_query_verification_missing_handler_fails_before_execution(
    tmp_path,
) -> None:
    service, history, events = make_verification_service(tmp_path, None)
    record_history(history, result_summary={"count": 1})

    with pytest.raises(
        RuntimeQueryNotFoundError,
        match="Runtime query not found: verification_query",
    ):
        service.verify("execution-1")

    failed = events.list_persisted_events(
        event_type="query_verification_failed"
    )
    assert failed[-1].severity.value == "error"
    assert failed[-1].metadata["query_version"] == 1


def test_query_verification_version_mismatch_is_predictable(
    tmp_path,
) -> None:
    handler = MutableVerificationQuery({"count": 1}, version=2)
    service, history, events = make_verification_service(
        tmp_path,
        handler,
    )
    record_history(history, result_summary={"count": 1}, version=1)

    with pytest.raises(
        QueryVersionMismatchError,
        match="historical=1, current=2",
    ) as exc_info:
        service.verify("execution-1")

    assert handler.calls == []
    assert exc_info.value.diagnostics[-1].event_type == (
        "query_verification_failed"
    )
    assert events.list_persisted_events(
        event_type="query_verification_failed"
    )


def test_query_verification_rejects_incomplete_reconstruction_metadata(
    tmp_path,
) -> None:
    handler = MutableVerificationQuery({"count": 1})
    service, _, events = make_verification_service(tmp_path, handler)
    execution_record = {
        "execution_id": "execution-1",
        "query_name": "verification_query",
        "query_version": 1,
        "executed_at": EXECUTED_AT.isoformat(),
        "parameters": {"scope": "session-1"},
        "execution_metadata": {
            "query_name": "verification_query",
            "query_version": 1,
            "handler_name": "MutableVerificationQuery",
            "execution_duration_ms": 4.0,
        },
        "success": True,
        "result_summary": {"count": 1},
    }
    events.emit_event_sync(
        event_type=EventType.QUERY_HISTORY_RECORDED,
        message="Incomplete reconstruction fixture",
        metadata={
            "execution_id": "execution-1",
            "query_name": "verification_query",
            "query_version": 1,
            "execution_record": execution_record,
            "reconstruction_info": {
                "query_name": "verification_query",
                "query_version": 1,
            },
        },
    )

    with pytest.raises(
        QueryReconstructionMetadataError,
        match="Incomplete query reconstruction metadata",
    ):
        service.verify("execution-1")

    assert handler.calls == []


def test_query_verification_diagnostics_include_identity(tmp_path) -> None:
    service, history, events = make_verification_service(
        tmp_path,
        MutableVerificationQuery({"count": 2}),
    )
    record_history(history, result_summary={"count": 1})

    result = service.verify("execution-1")

    assert result.verified is False
    verification_events = [
        event
        for event in events.list_persisted_events()
        if event.type.value.startswith("query_verification_")
    ]
    assert [event.type.value for event in verification_events] == [
        "query_verification_started",
        "query_verification_completed",
    ]
    for event in verification_events:
        assert event.metadata["execution_id"] == "execution-1"
        assert event.metadata["query_name"] == "verification_query"
        assert event.metadata["query_version"] == 1
        assert "verified" in event.metadata
        assert "difference_count" in event.metadata


def test_query_verification_endpoint_is_operational() -> None:
    session = runtime_session_service.create_session(
        "query-verification-endpoint-task"
    )
    client = TestClient(app)
    execution = client.post(
        f"/queries/{SESSION_DECISION_SUMMARY_QUERY_NAME}/execute",
        json={"parameters": {"session_id": session.id}},
    )
    execution_id = execution.json()["execution_id"]

    response = client.post(
        f"/queries/history/{execution_id}/verify"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["execution_id"] == execution_id
    assert body["query_name"] == SESSION_DECISION_SUMMARY_QUERY_NAME
    assert body["verified"] is True
    assert body["differences"] == []
    assert body["hash_match"] is True
    assert body["current_manifest"]["content_hash"] == (
        body["rebuilt_manifest"]["content_hash"]
    )
    assert body["reconstruction_info"]["parameter_snapshot"] == {
        "session_id": session.id
    }


def test_query_verification_endpoint_returns_unknown_execution() -> None:
    response = TestClient(app).post(
        "/queries/history/missing-execution/verify"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": (
            "Query execution record not found: missing-execution"
        )
    }
