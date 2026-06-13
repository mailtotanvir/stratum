from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType
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
from app.services.query_snapshot_export_service import (
    QuerySnapshotExportService,
)
from app.services.query_snapshot_manifest_service import (
    QuerySnapshotManifestService,
)
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


EXECUTED_AT = datetime(2026, 6, 13, 19, 0, tzinfo=UTC)


class ExportQueryHandler:
    def __init__(self) -> None:
        self.execute_count = 0

    def metadata(self) -> RuntimeQuery:
        return RuntimeQuery(
            query_name="export_query",
            query_version=5,
            description="Provide deterministic query export fixtures.",
            query_type="session_query",
            supported_parameters={
                "session_id": {"type": "string", "required": True}
            },
            result_schema={"type": "object"},
        )

    def execute(self, parameters: dict[str, Any]) -> dict[str, Any]:
        self.execute_count += 1
        return {"count": 1}


def make_export_service(tmp_path):
    events = EventService(TraceService(tmp_path / "query_export.db"))
    history = QueryHistoryService(events)
    registry = RuntimeQueryRegistry(
        events=events,
        emit_registration_diagnostics=False,
    )
    handler = ExportQueryHandler()
    registry.register(handler)
    lineage = QueryLineageService(
        registry=registry,
        history=history,
        events=events,
    )
    manifests = QuerySnapshotManifestService(
        history=history,
        lineage=lineage,
        events=events,
    )
    export_times = iter(
        [
            datetime(2026, 6, 13, 19, 5, tzinfo=UTC),
            datetime(2026, 6, 13, 19, 6, tzinfo=UTC),
        ]
    )
    export_ids = iter(["export-1", "export-2"])
    service = QuerySnapshotExportService(
        history=history,
        lineage=lineage,
        manifests=manifests,
        events=events,
        clock=lambda: next(export_times),
        id_factory=lambda: next(export_ids),
    )
    return service, history, handler, events


def record_execution(history: QueryHistoryService) -> None:
    history.record_execution(
        execution_id="execution-1",
        executed_at=EXECUTED_AT,
        parameters={"session_id": "session-1"},
        execution_metadata=RuntimeQueryExecutionMetadata(
            query_name="export_query",
            query_version=5,
            handler_name="ExportQueryHandler",
            execution_duration_ms=7.0,
        ),
        success=True,
        result_summary={"items": [{"id": "item-1"}], "count": 1},
    )


def stable_export_content(snapshot_export) -> dict[str, Any]:
    content = snapshot_export.model_dump(mode="json")
    content.pop("export_id")
    content.pop("exported_at")
    for diagnostic in content["diagnostics"]:
        diagnostic.pop("export_id")
    return content


def test_query_snapshot_export_is_complete_and_deterministic(
    tmp_path,
) -> None:
    service, history, handler, events = make_export_service(tmp_path)
    record_execution(history)
    events.emit_event_sync(
        event_type="decision_record_created",
        message="Export lineage source",
        metadata={
            "session_id": "session-1",
            "decision_id": "decision-1",
        },
    )

    first = service.export("execution-1")
    second = service.export("execution-1")

    assert first.export_id == "export-1"
    assert first.execution_id == "execution-1"
    assert first.query_execution_record.result_summary == {
        "items": [{"id": "item-1"}],
        "count": 1,
    }
    assert first.reconstruction_info.parameter_snapshot == {
        "session_id": "session-1"
    }
    assert first.lineage.source_identifiers["decision_ids"] == [
        "decision-1"
    ]
    assert first.manifest.generated_at == EXECUTED_AT
    assert first.manifest.parameter_hash
    assert first.manifest.result_hash
    assert first.manifest.content_hash
    assert first.verification_status is None
    assert handler.execute_count == 0
    assert stable_export_content(first) == stable_export_content(second)


def test_query_snapshot_export_includes_latest_verification_status(
    tmp_path,
) -> None:
    service, history, _, events = make_export_service(tmp_path)
    record_execution(history)
    events.emit_event_sync(
        event_type=EventType.QUERY_VERIFICATION_COMPLETED,
        message="Earlier verification",
        metadata={
            "execution_id": "execution-1",
            "query_name": "export_query",
            "query_version": 5,
            "verified": True,
            "difference_count": 0,
        },
    )
    events.emit_event_sync(
        event_type=EventType.QUERY_VERIFICATION_COMPLETED,
        message="Latest verification",
        metadata={
            "execution_id": "execution-1",
            "query_name": "export_query",
            "query_version": 5,
            "verified": False,
            "difference_count": 2,
        },
    )

    snapshot_export = service.export("execution-1")

    assert snapshot_export.verification_status is not None
    assert snapshot_export.verification_status.model_dump() == {
        "status": "drifted",
        "verified": False,
        "difference_count": 2,
    }


def test_query_snapshot_export_diagnostics_include_manifest_hash(
    tmp_path,
) -> None:
    service, history, _, events = make_export_service(tmp_path)
    record_execution(history)

    snapshot_export = service.export("execution-1")

    assert [
        diagnostic.event_type
        for diagnostic in snapshot_export.diagnostics
    ] == [
        "query_snapshot_export_started",
        "query_snapshot_export_completed",
    ]
    completed = events.list_persisted_events(
        event_type="query_snapshot_export_completed"
    )
    assert completed[-1].metadata == {
        "execution_id": "execution-1",
        "query_name": "export_query",
        "query_version": 5,
        "export_id": "export-1",
        "content_hash": snapshot_export.manifest.content_hash,
    }


def test_query_snapshot_export_unknown_execution_emits_failure(
    tmp_path,
) -> None:
    service, _, _, events = make_export_service(tmp_path)

    with pytest.raises(
        QueryExecutionRecordNotFoundError,
        match="Query execution record not found: missing-execution",
    ):
        service.export("missing-execution")

    failed = events.list_persisted_events(
        event_type="query_snapshot_export_failed"
    )
    assert failed[-1].metadata == {
        "execution_id": "missing-execution",
        "query_name": None,
        "query_version": None,
        "export_id": "export-1",
        "content_hash": None,
    }


def test_query_snapshot_export_endpoint_is_operational() -> None:
    session = runtime_session_service.create_session(
        "query-export-endpoint-task"
    )
    client = TestClient(app)
    execution = client.post(
        f"/queries/{SESSION_DECISION_SUMMARY_QUERY_NAME}/execute",
        json={"parameters": {"session_id": session.id}},
    )
    execution_id = execution.json()["execution_id"]

    response = client.post(
        f"/queries/history/{execution_id}/export"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["execution_id"] == execution_id
    assert body["query_execution_record"]["execution_id"] == execution_id
    assert body["reconstruction_info"]["parameter_snapshot"] == {
        "session_id": session.id
    }
    assert body["lineage"]["execution_id"] == execution_id
    assert body["manifest"]["execution_id"] == execution_id
    assert len(body["manifest"]["parameter_hash"]) == 64
    assert len(body["manifest"]["result_hash"]) == 64
    assert len(body["manifest"]["content_hash"]) == 64
    assert body["verification_status"] is None
    assert [
        diagnostic["event_type"] for diagnostic in body["diagnostics"]
    ] == [
        "query_snapshot_export_started",
        "query_snapshot_export_completed",
    ]


def test_query_snapshot_export_endpoint_includes_prior_verification() -> None:
    session = runtime_session_service.create_session(
        "verified-query-export-endpoint-task"
    )
    client = TestClient(app)
    execution = client.post(
        f"/queries/{SESSION_DECISION_SUMMARY_QUERY_NAME}/execute",
        json={"parameters": {"session_id": session.id}},
    )
    execution_id = execution.json()["execution_id"]
    verification = client.post(
        f"/queries/history/{execution_id}/verify"
    )
    assert verification.status_code == 200

    response = client.post(
        f"/queries/history/{execution_id}/export"
    )

    assert response.status_code == 200
    assert response.json()["verification_status"] == {
        "status": "verified",
        "verified": True,
        "difference_count": 0,
    }


def test_query_snapshot_export_endpoint_returns_unknown_execution() -> None:
    response = TestClient(app).post(
        "/queries/history/missing-execution/export"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": (
            "Query execution record not found: missing-execution"
        )
    }
