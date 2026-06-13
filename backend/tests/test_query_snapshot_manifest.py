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
from app.services.event_service import EventService
from app.services.query_history_service import (
    QueryExecutionRecordNotFoundError,
    QueryHistoryService,
)
from app.services.query_lineage_service import QueryLineageService
from app.services.query_snapshot_manifest_service import (
    QuerySnapshotManifestService,
    stable_query_hash,
)
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


EXECUTED_AT = datetime(2026, 6, 13, 18, 0, tzinfo=UTC)
GENERATED_AT = datetime(2026, 6, 13, 18, 5, tzinfo=UTC)


class ManifestQueryHandler:
    def metadata(self) -> RuntimeQuery:
        return RuntimeQuery(
            query_name="manifest_query",
            query_version=2,
            description="Provide deterministic manifest fixtures.",
            query_type="session_query",
            supported_parameters={
                "session_id": {"type": "string", "required": True},
                "filters": {"type": "object", "required": False},
            },
            result_schema={"type": "object"},
        )

    def execute(self, parameters: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("manifest generation must not execute handlers")


def make_manifest_service(tmp_path):
    events = EventService(TraceService(tmp_path / "query_manifest.db"))
    history = QueryHistoryService(events)
    registry = RuntimeQueryRegistry(
        events=events,
        emit_registration_diagnostics=False,
    )
    registry.register(ManifestQueryHandler())
    lineage = QueryLineageService(
        registry=registry,
        history=history,
        events=events,
    )
    service = QuerySnapshotManifestService(
        history=history,
        lineage=lineage,
        events=events,
        clock=lambda: GENERATED_AT,
    )
    return service, history, lineage, events


def record_execution(history: QueryHistoryService) -> None:
    history.record_execution(
        execution_id="execution-1",
        executed_at=EXECUTED_AT,
        parameters={
            "filters": {"status": "active", "limit": 2},
            "session_id": "session-1",
        },
        execution_metadata=RuntimeQueryExecutionMetadata(
            query_name="manifest_query",
            query_version=2,
            handler_name="ManifestQueryHandler",
            execution_duration_ms=8.0,
        ),
        success=True,
        result_summary={
            "items": [{"id": "item-1"}],
            "count": 1,
        },
    )


def test_query_manifest_generation_is_deterministic(tmp_path) -> None:
    service, history, lineage, events = make_manifest_service(tmp_path)
    record_execution(history)
    expected_lineage = lineage.generate("execution-1")

    first = service.generate("execution-1")
    second = service.generate("execution-1")

    assert first == second
    assert first.model_dump(mode="json") == {
        "execution_id": "execution-1",
        "query_name": "manifest_query",
        "query_version": 2,
        "handler_name": "ManifestQueryHandler",
        "generated_at": "2026-06-13T18:05:00Z",
        "parameter_hash": stable_query_hash(
            {
                "filters": {"status": "active", "limit": 2},
                "session_id": "session-1",
            }
        ),
        "result_hash": stable_query_hash(
            {
                "items": [{"id": "item-1"}],
                "count": 1,
            }
        ),
        "lineage_version": expected_lineage.lineage_version,
        "reconstruction_version": (
            expected_lineage.reconstruction_info.reconstruction_version
        ),
        "content_hash": first.content_hash,
    }
    assert len(first.parameter_hash) == 64
    assert len(first.result_hash) == 64
    assert len(first.content_hash) == 64
    assert first.content_hash == second.content_hash
    assert len(
        events.list_persisted_events(
            event_type="query_manifest_generated"
        )
    ) == 2


def test_query_hash_is_stable_and_excludes_volatile_timestamps() -> None:
    first = {
        "generated_at": "2026-06-13T12:00:00Z",
        "parameters": {"beta": 2, "alpha": 1},
    }
    second = {
        "parameters": {"alpha": 1, "beta": 2},
        "generated_at": "2026-06-14T12:00:00Z",
    }

    assert stable_query_hash(first) == stable_query_hash(second)
    assert stable_query_hash(
        first,
        include_volatile=True,
    ) != stable_query_hash(
        second,
        include_volatile=True,
    )


def test_parameter_and_result_hashes_change_independently(tmp_path) -> None:
    service, history, _, _ = make_manifest_service(tmp_path)
    record_execution(history)

    original = service.generate("execution-1")
    changed_result = service.generate(
        "execution-1",
        result_summary={"count": 2, "items": []},
    )

    assert original.parameter_hash == changed_result.parameter_hash
    assert original.result_hash != changed_result.result_hash
    assert original.content_hash != changed_result.content_hash
    assert stable_query_hash({"value": 1}) != stable_query_hash(
        {"value": 2}
    )


def test_query_manifest_diagnostics_include_content_hash(tmp_path) -> None:
    service, history, _, events = make_manifest_service(tmp_path)
    record_execution(history)

    manifest = service.generate("execution-1")

    for event_type in [
        "query_manifest_hash_computed",
        "query_manifest_generated",
    ]:
        matching = events.list_persisted_events(event_type=event_type)
        assert matching[-1].metadata == {
            "execution_id": "execution-1",
            "query_name": "manifest_query",
            "query_version": 2,
            "content_hash": manifest.content_hash,
        }


def test_query_manifest_unknown_execution_emits_failure(tmp_path) -> None:
    service, _, _, events = make_manifest_service(tmp_path)

    with pytest.raises(
        QueryExecutionRecordNotFoundError,
        match="Query execution record not found: missing-execution",
    ):
        service.generate("missing-execution")

    failed = events.list_persisted_events(
        event_type="query_manifest_generation_failed"
    )
    assert failed[-1].metadata == {
        "execution_id": "missing-execution",
        "query_name": None,
        "query_version": None,
        "content_hash": None,
    }


def test_query_manifest_endpoint_is_operational() -> None:
    session = runtime_session_service.create_session(
        "query-manifest-endpoint-task"
    )
    client = TestClient(app)
    execution = client.post(
        f"/queries/{SESSION_DECISION_SUMMARY_QUERY_NAME}/execute",
        json={"parameters": {"session_id": session.id}},
    )
    execution_id = execution.json()["execution_id"]

    response = client.get(
        f"/queries/history/{execution_id}/manifest"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["execution_id"] == execution_id
    assert body["query_name"] == SESSION_DECISION_SUMMARY_QUERY_NAME
    assert body["handler_name"] == "SessionDecisionSummaryQuery"
    assert body["lineage_version"] == 1
    assert body["reconstruction_version"] == 1
    assert len(body["parameter_hash"]) == 64
    assert len(body["result_hash"]) == 64
    assert len(body["content_hash"]) == 64


def test_query_manifest_endpoint_returns_unknown_execution() -> None:
    response = TestClient(app).get(
        "/queries/history/missing-execution/manifest"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": (
            "Query execution record not found: missing-execution"
        )
    }
