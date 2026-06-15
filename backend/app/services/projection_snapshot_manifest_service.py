import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from app.models.projection import (
    ProjectionSchemaInfo,
    ProjectionSnapshotManifest,
)
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.runtime.projection_contract_validator import validate_projection_result
from app.runtime.projection_registry import (
    ProjectionRegistry,
    projection_registry,
)
from app.services.event_service import EventService, event_service


VOLATILE_HASH_FIELDS = frozenset(
    {
        "built_at",
        "generated_at",
        "verified_at",
    }
)

NON_SOURCE_EVENT_TYPES = frozenset(
    {
        EventType.DECISION_PROJECTION_BUILT.value,
        EventType.SESSION_DECISION_PROJECTION_BUILT.value,
        EventType.PROJECTION_REBUILD_STARTED.value,
        EventType.PROJECTION_REBUILD_COMPLETED.value,
        EventType.PROJECTION_REBUILD_FAILED.value,
        EventType.PROJECTION_REPLAY_STARTED.value,
        EventType.PROJECTION_REPLAY_COMPLETED.value,
        EventType.PROJECTION_REPLAY_FAILED.value,
        EventType.PROJECTION_REPLAY_DRY_RUN_COMPLETED.value,
        EventType.PROJECTION_DRIFT_CHECK_STARTED.value,
        EventType.PROJECTION_DRIFT_CHECK_COMPLETED.value,
        EventType.PROJECTION_DRIFT_DETECTED.value,
        EventType.PROJECTION_DRIFT_CHECK_FAILED.value,
        EventType.GOVERNANCE_PROJECTION_UPDATED.value,
        EventType.GOVERNANCE_DECISION_RECORDED.value,
        EventType.GOVERNANCE_PROJECTION_REBUILT.value,
        EventType.DECISION_LINEAGE_UPDATED.value,
        EventType.DECISION_LINEAGE_REBUILT.value,
        EventType.DECISION_LINEAGE_INCOMPLETE.value,
        EventType.DECISION_LINEAGE_RECONSTRUCTION_FAILED.value,
        EventType.ARTIFACT_LINEAGE_UPDATED.value,
        EventType.ARTIFACT_LINEAGE_REBUILT.value,
        EventType.ARTIFACT_LINEAGE_INCOMPLETE.value,
        EventType.ARTIFACT_LINEAGE_RECONSTRUCTION_FAILED.value,
        EventType.PROJECTION_VERIFICATION_STARTED.value,
        EventType.PROJECTION_VERIFICATION_COMPLETED.value,
        EventType.PROJECTION_VERIFICATION_FAILED.value,
        EventType.PROJECTION_MANIFEST_GENERATED.value,
        EventType.PROJECTION_MANIFEST_HASH_COMPUTED.value,
        EventType.PROJECTION_MANIFEST_GENERATION_FAILED.value,
        EventType.PROJECTION_SNAPSHOT_EXPORT_STARTED.value,
        EventType.PROJECTION_SNAPSHOT_EXPORT_COMPLETED.value,
        EventType.PROJECTION_SNAPSHOT_EXPORT_FAILED.value,
        EventType.PROJECTION_LINEAGE_GENERATED.value,
        EventType.PROJECTION_LINEAGE_GENERATION_FAILED.value,
        EventType.RUNTIME_QUERY_REGISTERED.value,
        EventType.RUNTIME_QUERY_DISCOVERED.value,
        EventType.RUNTIME_QUERY_EXECUTED.value,
        EventType.RUNTIME_QUERY_EXECUTION_STARTED.value,
        EventType.RUNTIME_QUERY_EXECUTION_COMPLETED.value,
        EventType.RUNTIME_QUERY_EXECUTION_FAILED.value,
        EventType.RUNTIME_RECONSTRUCTION_VIEW_BUILT.value,
        EventType.RUNTIME_RECONSTRUCTION_VIEW_INCOMPLETE.value,
        EventType.RUNTIME_RECONSTRUCTION_VIEW_FAILED.value,
    }
)


class ProjectionManifestGenerationError(RuntimeError):
    pass


class ProjectionSnapshotManifestService:
    def __init__(
        self,
        registry: ProjectionRegistry | None = None,
        events: EventService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._registry = registry or projection_registry
        self._events = events or event_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def current_manifest(
        self,
        projection_name: str,
        source_session_id: str,
    ) -> ProjectionSnapshotManifest:
        builder = self._registry.get(projection_name)
        schema = self._registry.get_schema(projection_name)
        try:
            projection_data = builder.build(source_session_id)
            validate_projection_result(projection_data, schema)
        except Exception as exc:
            self._emit_failure(schema, source_session_id, exc)
            raise ProjectionManifestGenerationError(
                f"Projection manifest generation failed: {exc}"
            ) from exc
        return self.generate(
            schema,
            projection_data,
            source_session_id,
        )

    def generate(
        self,
        schema: ProjectionSchemaInfo,
        projection_data: Any,
        source_session_id: str,
        verification_status: str | None = None,
    ) -> ProjectionSnapshotManifest:
        try:
            source_event_count = self._source_event_count(source_session_id)
            content_hash = stable_projection_content_hash(projection_data)
            manifest = ProjectionSnapshotManifest(
                projection_name=schema.projection_type,
                schema_version=schema.schema_version,
                builder_name=schema.builder_name,
                generated_at=self._clock(),
                source_event_count=source_event_count,
                source_session_id=source_session_id,
                source_runtime_id=None,
                reconstruction_info=schema.reconstruction,
                verification_status=verification_status,
                content_hash=content_hash,
            )
        except Exception as exc:
            self._emit_failure(schema, source_session_id, exc)
            raise ProjectionManifestGenerationError(
                f"Projection manifest generation failed: {exc}"
            ) from exc

        diagnostic_metadata = {
            "projection_name": schema.projection_type,
            "schema_version": schema.schema_version,
            "builder_name": schema.builder_name,
            "source_session_id": source_session_id,
            "source_event_count": source_event_count,
            "content_hash": content_hash,
        }
        self._events.emit_event_sync(
            event_type=EventType.PROJECTION_MANIFEST_HASH_COMPUTED,
            message=f"Projection manifest hash computed: {schema.projection_type}",
            metadata=diagnostic_metadata,
        )
        self._events.emit_event_sync(
            event_type=EventType.PROJECTION_MANIFEST_GENERATED,
            message=f"Projection manifest generated: {schema.projection_type}",
            metadata=diagnostic_metadata,
        )
        return manifest

    def _source_event_count(self, source_session_id: str) -> int:
        return len(
            projection_source_events(
                self._events.list_persisted_events(),
                source_session_id,
            )
        )

    def _emit_failure(
        self,
        schema: ProjectionSchemaInfo,
        source_session_id: str,
        exc: Exception,
    ) -> None:
        self._events.emit_event_sync(
            event_type=EventType.PROJECTION_MANIFEST_GENERATION_FAILED,
            severity=Severity.ERROR,
            message=f"Projection manifest generation failed: {exc}",
            metadata={
                "projection_name": schema.projection_type,
                "schema_version": schema.schema_version,
                "builder_name": schema.builder_name,
                "source_session_id": source_session_id,
            },
        )


def stable_projection_content_hash(
    projection_content: Any,
    include_volatile: bool = False,
) -> str:
    normalized = normalize_projection_content(
        projection_content,
        include_volatile=include_volatile,
    )
    serialized = json.dumps(
        normalized,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def normalize_projection_content(
    value: Any,
    include_volatile: bool = False,
) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {
            key: normalize_projection_content(
                item,
                include_volatile=include_volatile,
            )
            for key, item in sorted(value.items())
            if include_volatile or key not in VOLATILE_HASH_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [
            normalize_projection_content(
                item,
                include_volatile=include_volatile,
            )
            for item in value
        ]
    return value


def projection_source_events(
    events: list[RuntimeEvent],
    source_session_id: str,
) -> list[RuntimeEvent]:
    return [
        event
        for event in events
        if event.metadata.get("session_id") == source_session_id
        and event.type.value not in NON_SOURCE_EVENT_TYPES
    ]


projection_snapshot_manifest_service = ProjectionSnapshotManifestService()
