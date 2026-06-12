from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_query import RuntimeQuery
from app.models.runtime_query_execution import RuntimeQueryExecutionRequest
from app.query.runtime_query_registry import (
    RuntimeQueryNotFoundError,
    RuntimeQueryRegistry,
)
from app.query.session_decision_summary_query import (
    SESSION_DECISION_SUMMARY_QUERY_NAME,
)
from app.services.event_service import EventService, event_service
from app.services.runtime_query_execution_service import (
    RuntimeQueryExecutionService,
    RuntimeQueryParameterValidationError,
)
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


class RecordingExecutionHandler:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def metadata(self) -> RuntimeQuery:
        return RuntimeQuery(
            query_name="recording_query",
            query_version=3,
            description="Record strictly validated query parameters.",
            query_type="diagnostic_query",
            supported_parameters={
                "name": {"type": "string", "required": True},
                "limit": {"type": "integer", "required": False},
            },
            result_schema={"type": "object"},
        )

    def execute(self, parameters: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(parameters)
        return {"parameters": parameters}


def make_execution_service(tmp_path):
    events = EventService(TraceService(tmp_path / "query_execution.db"))
    registry = RuntimeQueryRegistry(
        events=events,
        emit_registration_diagnostics=False,
    )
    handler = RecordingExecutionHandler()
    registry.register(handler)
    timer_values = iter([10.0, 10.025])
    service = RuntimeQueryExecutionService(
        registry=registry,
        events=events,
        clock=lambda: datetime(2026, 6, 12, 14, 0, tzinfo=UTC),
        timer=lambda: next(timer_values),
        id_factory=lambda: "execution-1",
    )
    return service, handler, events


def execution_request(parameters: dict[str, Any]):
    return RuntimeQueryExecutionRequest(
        query_name="recording_query",
        parameters=parameters,
        execution_context={"request_source": "test"},
        requested_at=datetime(2026, 6, 12, 13, 59, tzinfo=UTC),
    )


def test_runtime_query_execution_service_executes_through_registry(
    tmp_path,
) -> None:
    service, handler, events = make_execution_service(tmp_path)

    result = service.execute(
        execution_request({"name": "runtime", "limit": 2})
    )

    assert handler.calls == [{"name": "runtime", "limit": 2}]
    assert result.model_dump(mode="json") == {
        "query_name": "recording_query",
        "execution_id": "execution-1",
        "executed_at": "2026-06-12T14:00:00Z",
        "success": True,
        "result": {
            "parameters": {"name": "runtime", "limit": 2}
        },
        "diagnostics": [
            {
                "event_type": "runtime_query_execution_started",
                "query_name": "recording_query",
                "execution_id": "execution-1",
                "duration_ms": 0.0,
                "success": False,
            },
            {
                "event_type": "runtime_query_execution_completed",
                "query_name": "recording_query",
                "execution_id": "execution-1",
                "duration_ms": 25.0,
                "success": True,
            },
        ],
        "execution_metadata": {
            "query_name": "recording_query",
            "query_version": 3,
            "handler_name": "RecordingExecutionHandler",
            "execution_duration_ms": 25.0,
        },
    }
    assert [
        event.type.value for event in events.list_persisted_events()
    ] == [
        "runtime_query_execution_started",
        "runtime_query_execution_completed",
        "runtime_query_executed",
    ]


@pytest.mark.parametrize(
    ("parameters", "expected_issues"),
    [
        (
            {"extra": "unsupported"},
            [
                ("extra", "unknown_parameter"),
                ("name", "missing_parameter"),
            ],
        ),
        (
            {"name": 42, "limit": True},
            [
                ("limit", "invalid_parameter_type"),
                ("name", "invalid_parameter_type"),
            ],
        ),
    ],
)
def test_runtime_query_parameter_validation_is_strict_and_structured(
    tmp_path,
    parameters,
    expected_issues,
) -> None:
    service, handler, events = make_execution_service(tmp_path)

    with pytest.raises(
        RuntimeQueryParameterValidationError
    ) as exc_info:
        service.execute(execution_request(parameters))

    assert handler.calls == []
    assert [
        (issue.parameter, issue.error_type)
        for issue in exc_info.value.issues
    ] == expected_issues
    assert [
        event.type.value for event in events.list_persisted_events()
    ] == [
        "runtime_query_execution_started",
        "runtime_query_execution_failed",
    ]
    assert events.list_persisted_events()[-1].metadata["success"] is False


def test_unknown_query_emits_failed_execution_diagnostic(tmp_path) -> None:
    events = EventService(TraceService(tmp_path / "unknown_query.db"))
    service = RuntimeQueryExecutionService(
        registry=RuntimeQueryRegistry(
            events=events,
            emit_registration_diagnostics=False,
        ),
        events=events,
        timer=lambda: 5.0,
        id_factory=lambda: "missing-execution",
    )

    with pytest.raises(
        RuntimeQueryNotFoundError,
        match="Runtime query not found: missing_query",
    ):
        service.execute(
            RuntimeQueryExecutionRequest(
                query_name="missing_query",
                parameters={},
                execution_context={},
                requested_at=datetime.now(UTC),
            )
        )

    failed = events.list_persisted_events(
        event_type="runtime_query_execution_failed"
    )
    assert len(failed) == 1
    assert failed[0].metadata == {
        "query_name": "missing_query",
        "execution_id": "missing-execution",
        "duration_ms": 0.0,
        "success": False,
    }


def test_query_execution_endpoint_uses_execution_pipeline() -> None:
    session = runtime_session_service.create_session(
        "runtime-query-execution-endpoint-task"
    )

    response = TestClient(app).post(
        f"/queries/{SESSION_DECISION_SUMMARY_QUERY_NAME}/execute",
        json={"parameters": {"session_id": session.id}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["query_name"] == SESSION_DECISION_SUMMARY_QUERY_NAME
    assert body["execution_metadata"]["query_version"] == 1
    assert body["execution_metadata"]["handler_name"] == (
        "SessionDecisionSummaryQuery"
    )
    assert body["execution_metadata"]["execution_duration_ms"] >= 0
    assert [
        diagnostic["event_type"] for diagnostic in body["diagnostics"]
    ] == [
        "runtime_query_execution_started",
        "runtime_query_execution_completed",
    ]
    assert len(
        event_service.list_persisted_events(
            event_type="runtime_query_execution_completed"
        )
    ) == 1


def test_query_execution_endpoint_returns_structured_parameter_errors() -> None:
    response = TestClient(app).post(
        f"/queries/{SESSION_DECISION_SUMMARY_QUERY_NAME}/execute",
        json={
            "parameters": {
                "session_id": 123,
                "unexpected": "value",
            }
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["query_name"] == SESSION_DECISION_SUMMARY_QUERY_NAME
    assert [
        (issue["parameter"], issue["error_type"])
        for issue in detail["issues"]
    ] == [
        ("unexpected", "unknown_parameter"),
        ("session_id", "invalid_parameter_type"),
    ]
