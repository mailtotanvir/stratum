from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.models.projection import ProjectionSchemaInfo
from app.models.projection_lineage import ProjectionLineage
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.runtime.projection_registry import (
    ProjectionRegistry,
    projection_registry,
)
from app.services.event_service import EventService, event_service
from app.services.projection_snapshot_manifest_service import (
    NON_SOURCE_EVENT_TYPES,
)
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)


LINEAGE_VERSION = 1
EVENT_ACTION_SUFFIXES = (
    "_attached",
    "_blocked",
    "_completed",
    "_created",
    "_disabled",
    "_dismissed",
    "_enabled",
    "_failed",
    "_generated",
    "_ignored",
    "_interrupted",
    "_promoted",
    "_requested",
    "_resolved",
    "_responded",
    "_running",
    "_started",
    "_stopped",
)


class ProjectionLineageGenerationError(RuntimeError):
    pass


class ProjectionLineageService:
    def __init__(
        self,
        registry: ProjectionRegistry | None = None,
        events: EventService | None = None,
        sessions: RuntimeSessionService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._registry = registry or projection_registry
        self._events = events or event_service
        self._sessions = sessions or runtime_session_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def generate(
        self,
        projection_name: str,
        source: str,
    ) -> ProjectionLineage:
        self._registry.get(projection_name)
        schema = self._registry.get_schema(projection_name)
        try:
            session = self._sessions.get_session(source)
            source_events = self._source_events(source)
            source_types, source_counts = self._source_description(
                schema,
                source_events,
            )
            source_identifiers = self._source_identifiers(
                session.task_id,
                source,
                source_events,
            )
            lineage = ProjectionLineage(
                projection_name=schema.projection_type,
                builder_name=schema.builder_name,
                schema_version=schema.schema_version,
                generated_at=session.created_at,
                reconstruction_info=schema.reconstruction.model_dump(),
                source_types=source_types,
                source_identifiers=source_identifiers,
                source_counts=source_counts,
                lineage_version=LINEAGE_VERSION,
            )
        except Exception as exc:
            self._emit_failure(schema, exc)
            raise ProjectionLineageGenerationError(
                f"Projection lineage generation failed: {exc}"
            ) from exc

        self._events.emit_event_sync(
            event_type=EventType.PROJECTION_LINEAGE_GENERATED,
            message=f"Projection lineage generated: {schema.projection_type}",
            metadata={
                "projection_name": schema.projection_type,
                "builder_name": schema.builder_name,
                "schema_version": schema.schema_version,
                "source_count": 1 + len(source_events),
            },
        )
        return lineage

    def _source_events(self, source: str) -> list[RuntimeEvent]:
        return [
            event
            for event in self._events.list_persisted_events()
            if event.metadata.get("session_id") == source
            and event.type.value not in NON_SOURCE_EVENT_TYPES
        ]

    def _source_description(
        self,
        schema: ProjectionSchemaInfo,
        source_events: list[RuntimeEvent],
    ) -> tuple[list[str], dict[str, int]]:
        source_counts: Counter[str] = Counter()
        source_counts[schema.reconstruction.authoritative_source] += 1
        if source_events:
            source_counts["runtime_event"] = len(source_events)
        for event in source_events:
            source_counts[_event_source_type(event.type.value)] += 1

        source_types = {
            schema.reconstruction.authoritative_source,
            schema.reconstruction.reconstruction_source,
            *source_counts.keys(),
        }
        return (
            sorted(source_types),
            dict(sorted(source_counts.items())),
        )

    def _source_identifiers(
        self,
        task_id: str,
        session_id: str,
        source_events: list[RuntimeEvent],
    ) -> dict[str, Any]:
        discovered: defaultdict[str, set[str | int]] = defaultdict(set)
        for event in source_events:
            for key, value in event.metadata.items():
                if not key.endswith("_id") or key in {"session_id", "task_id"}:
                    continue
                if isinstance(value, (str, int)):
                    discovered[f"{key[:-3]}_ids"].add(value)

        identifiers: dict[str, Any] = {
            "event_ids": [event.id for event in source_events],
            "session_id": session_id,
            "task_id": task_id,
        }
        for key in sorted(discovered):
            identifiers[key] = sorted(
                discovered[key],
                key=lambda value: str(value),
            )
        return identifiers

    def _emit_failure(
        self,
        schema: ProjectionSchemaInfo,
        exc: Exception,
    ) -> None:
        self._events.emit_event_sync(
            event_type=EventType.PROJECTION_LINEAGE_GENERATION_FAILED,
            severity=Severity.ERROR,
            message=f"Projection lineage generation failed: {exc}",
            metadata={
                "projection_name": schema.projection_type,
                "builder_name": schema.builder_name,
                "schema_version": schema.schema_version,
                "source_count": 0,
            },
        )


def _event_source_type(event_type: str) -> str:
    for suffix in EVENT_ACTION_SUFFIXES:
        if event_type.endswith(suffix):
            return event_type[: -len(suffix)]
    return event_type


projection_lineage_service = ProjectionLineageService()
