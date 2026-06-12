from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.projection import (
    Projection,
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.runtime.projection_registry import (
    ProjectionRegistry,
    ProjectionTypeNotFoundError,
)
from app.services.event_service import EventService
from app.services.projection_rebuild_service import ProjectionRebuildService
from app.services.projection_verification_service import (
    ProjectionVerificationError,
    ProjectionVerificationService,
    compare_projection_values,
)
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


class VerificationProjection(Projection):
    value: str
    details: dict[str, str]


class SequenceProjectionBuilder:
    projection_type = "verification_projection"
    schema_info = ProjectionSchemaInfo(
        projection_type=projection_type,
        schema_version=1,
        builder_name="SequenceProjectionBuilder",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=projection_type,
            reconstruction_source="runtime_session_state",
            authoritative_source="runtime_session",
        ),
    )

    def __init__(
        self,
        values: list[str],
        metadata_mismatch: bool = False,
    ) -> None:
        self._values = iter(values)
        self._metadata_mismatch = metadata_mismatch
        self.returned: list[VerificationProjection] = []

    def build(self, source: str) -> VerificationProjection:
        build_index = len(self.returned)
        metadata = self.schema_info.model_dump()
        if self._metadata_mismatch and build_index == 0:
            metadata["reconstruction"]["reconstruction_source"] = (
                "stale_runtime_state"
            )
        projection = VerificationProjection(
            metadata=ProjectionMetadata(
                **metadata,
                built_at=datetime(
                    2026,
                    6,
                    11,
                    12,
                    build_index,
                    tzinfo=UTC,
                ),
                source="sequence_projection_builder",
            ),
            value=next(self._values),
            details={"source": source},
        )
        self.returned.append(projection)
        return projection


class FailingProjectionBuilder(SequenceProjectionBuilder):
    def build(self, source: str) -> VerificationProjection:
        raise RuntimeError("current projection unavailable")


def make_verification_service(
    tmp_path,
    builder: SequenceProjectionBuilder,
) -> tuple[ProjectionVerificationService, EventService]:
    registry = ProjectionRegistry()
    registry.register(builder)
    events = EventService(TraceService(tmp_path / "projection_verification.db"))
    rebuilds = ProjectionRebuildService(registry, events)
    return (
        ProjectionVerificationService(
            registry=registry,
            rebuilds=rebuilds,
            events=events,
            clock=lambda: datetime(2026, 6, 11, 13, 0, tzinfo=UTC),
        ),
        events,
    )


def test_projection_verification_succeeds_without_mutating_projection(
    tmp_path,
) -> None:
    builder = SequenceProjectionBuilder(["stable", "stable"])
    service, events = make_verification_service(tmp_path, builder)

    result = service.verify("verification_projection", "session-1")

    assert result.verified is True
    assert result.differences == []
    assert result.verified_at == datetime(2026, 6, 11, 13, 0, tzinfo=UTC)
    assert result.reconstruction_info == builder.schema_info.reconstruction
    assert result.hash_match is True
    assert result.current_manifest.content_hash == (
        result.rebuilt_manifest.content_hash
    )
    assert builder.returned[0].value == "stable"
    assert builder.returned[0].metadata.built_at == datetime(
        2026,
        6,
        11,
        12,
        0,
        tzinfo=UTC,
    )
    verification_events = [
        event
        for event in events.list_persisted_events()
        if event.type.value.startswith("projection_verification_")
    ]
    assert [event.type.value for event in verification_events] == [
        "projection_verification_started",
        "projection_verification_completed",
    ]
    assert verification_events[-1].metadata["difference_count"] == 0


def test_projection_verification_detects_value_drift(tmp_path) -> None:
    builder = SequenceProjectionBuilder(["stale", "rebuilt"])
    service, events = make_verification_service(tmp_path, builder)

    result = service.verify("verification_projection", "session-1")

    assert result.verified is False
    assert result.hash_match is False
    assert [difference.model_dump() for difference in result.differences] == [
        {
            "field_path": "$.value",
            "expected_value": "rebuilt",
            "actual_value": "stale",
            "difference_type": "value_mismatch",
        }
    ]
    completed = events.list_persisted_events(
        event_type="projection_verification_completed"
    )
    assert completed[0].metadata == {
        "projection_name": "verification_projection",
        "schema_version": 1,
        "builder_name": "SequenceProjectionBuilder",
        "difference_count": 1,
    }


def test_projection_difference_generation_is_generic_and_deterministic() -> None:
    differences = compare_projection_values(
        {
            "alpha": 1,
            "items": [{"kept": True}, {"missing": "expected"}],
        },
        {
            "alpha": 2,
            "items": [{"extra": "actual", "kept": True}],
        },
    )

    assert [difference.model_dump() for difference in differences] == [
        {
            "field_path": "$.alpha",
            "expected_value": 1,
            "actual_value": 2,
            "difference_type": "value_mismatch",
        },
        {
            "field_path": "$.items[0].extra",
            "expected_value": None,
            "actual_value": "actual",
            "difference_type": "unexpected_field",
        },
        {
            "field_path": "$.items[1]",
            "expected_value": {"missing": "expected"},
            "actual_value": None,
            "difference_type": "missing_field",
        },
    ]


def test_projection_verification_detects_metadata_mismatch(tmp_path) -> None:
    builder = SequenceProjectionBuilder(
        ["stable", "stable"],
        metadata_mismatch=True,
    )
    service, _ = make_verification_service(tmp_path, builder)

    result = service.verify("verification_projection", "session-1")

    assert result.verified is False
    assert result.hash_match is False
    assert [difference.model_dump() for difference in result.differences] == [
        {
            "field_path": (
                "$.metadata.reconstruction.reconstruction_source"
            ),
            "expected_value": "runtime_session_state",
            "actual_value": "stale_runtime_state",
            "difference_type": "metadata_mismatch",
        }
    ]


def test_projection_verification_unknown_projection_is_clean(tmp_path) -> None:
    registry = ProjectionRegistry()
    service = ProjectionVerificationService(
        registry=registry,
        rebuilds=ProjectionRebuildService(registry),
    )

    with pytest.raises(
        ProjectionTypeNotFoundError,
        match="Projection type not found: missing_projection",
    ):
        service.verify("missing_projection", "session-1")


def test_projection_verification_failure_emits_diagnostic(tmp_path) -> None:
    builder = FailingProjectionBuilder(["unused"])
    service, events = make_verification_service(tmp_path, builder)

    with pytest.raises(ProjectionVerificationError) as exc_info:
        service.verify("verification_projection", "session-1")

    assert "current projection unavailable" in str(exc_info.value)
    assert [
        diagnostic.event_type
        for diagnostic in exc_info.value.diagnostics
    ] == [
        "projection_verification_started",
        "projection_verification_failed",
    ]
    failed = events.list_persisted_events(
        event_type="projection_verification_failed"
    )
    assert len(failed) == 1
    assert failed[0].severity.value == "error"


def test_projection_verification_endpoint_is_operational() -> None:
    session = runtime_session_service.create_session(
        "projection-verification-endpoint-task"
    )

    response = TestClient(app).get(
        "/projections/decision_projection/verify",
        params={"source": session.id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True
    assert body["projection_name"] == "decision_projection"
    assert body["differences"] == []
    assert body["hash_match"] is True
    assert body["current_manifest"]["content_hash"] == (
        body["rebuilt_manifest"]["content_hash"]
    )
    assert body["reconstruction_info"]["authoritative_source"] == (
        "runtime_session"
    )


def test_projection_verification_endpoint_returns_unknown_projection() -> None:
    response = TestClient(app).get(
        "/projections/missing_projection/verify",
        params={"source": "session-1"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Projection type not found: missing_projection"
    }
