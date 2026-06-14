from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.models.projection import ProjectionSchemaInfo
from app.models.projection_lifecycle import (
    ProjectionLifecycleStatus,
    ProjectionRebuildHistory,
    ProjectionRebuildRecord,
)
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.runtime.projection_registry import (
    ProjectionRegistry,
    projection_registry,
)
from app.services.event_service import EventService, event_service
from app.services.projection_snapshot_manifest_service import (
    projection_source_events,
)


TERMINAL_REBUILD_EVENT_TYPES = frozenset(
    {
        EventType.PROJECTION_REBUILD_COMPLETED,
        EventType.PROJECTION_REBUILD_FAILED,
    }
)


@dataclass(frozen=True)
class ProjectionRebuildHandle:
    start_event_id: int
    schema: ProjectionSchemaInfo
    source: str
    record: ProjectionRebuildRecord


class ProjectionLifecycleService:
    def __init__(
        self,
        registry: ProjectionRegistry | None = None,
        events: EventService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._registry = registry or projection_registry
        self._events = events or event_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def register_rebuild_start(
        self,
        schema: ProjectionSchemaInfo,
        source: str,
        diagnostic_metadata: dict[str, Any],
    ) -> ProjectionRebuildHandle:
        started_at = self._clock()
        source_events = self._source_events(source)
        record = ProjectionRebuildRecord(
            projection_name=schema.projection_type,
            projection_version=schema.schema_version,
            rebuild_started_at=started_at,
            status="started",
            source_event_count=len(source_events),
            source_event_range_start=(
                source_events[0].id if source_events else None
            ),
            source_event_range_end=(
                source_events[-1].id if source_events else None
            ),
        )
        event = self._events.emit_event_sync(
            event_type=EventType.PROJECTION_REBUILD_STARTED,
            message="Projection rebuild started",
            metadata={
                **diagnostic_metadata,
                **record.model_dump(mode="json"),
            },
        )
        return ProjectionRebuildHandle(
            start_event_id=event.id,
            schema=schema.model_copy(deep=True),
            source=source,
            record=record,
        )

    def register_rebuild_completion(
        self,
        handle: ProjectionRebuildHandle,
        diagnostic_metadata: dict[str, Any],
    ) -> ProjectionRebuildRecord:
        return self._register_terminal(
            handle,
            status="completed",
            event_type=EventType.PROJECTION_REBUILD_COMPLETED,
            severity=Severity.INFO,
            message="Projection rebuild completed",
            diagnostic_metadata=diagnostic_metadata,
        )

    def register_rebuild_failure(
        self,
        handle: ProjectionRebuildHandle,
        diagnostic_metadata: dict[str, Any],
        message: str,
    ) -> ProjectionRebuildRecord:
        return self._register_terminal(
            handle,
            status="failed",
            event_type=EventType.PROJECTION_REBUILD_FAILED,
            severity=Severity.ERROR,
            message=message,
            diagnostic_metadata=diagnostic_metadata,
        )

    def rebuild_history(self) -> ProjectionRebuildHistory:
        records_by_start_event: dict[int, ProjectionRebuildRecord] = {}
        pending_by_projection_source: dict[
            tuple[str, str], list[int]
        ] = {}
        for event in self._rebuild_events():
            if event.type == EventType.PROJECTION_REBUILD_STARTED:
                records_by_start_event[event.id] = self._start_record(event)
                key = self._projection_source_key(event)
                pending_by_projection_source.setdefault(key, []).append(
                    event.id
                )
                continue
            start_event_id = event.metadata.get("rebuild_start_event_id")
            if not isinstance(start_event_id, int):
                pending = pending_by_projection_source.get(
                    self._projection_source_key(event),
                    [],
                )
                start_event_id = pending.pop() if pending else None
            if (
                isinstance(start_event_id, int)
                and start_event_id in records_by_start_event
            ):
                records_by_start_event[start_event_id] = (
                    self._terminal_record(
                        event,
                        records_by_start_event[start_event_id],
                    )
                )

        ordered = [
            record
            for _, record in sorted(
                records_by_start_event.items(),
                key=lambda item: (
                    item[1].rebuild_started_at,
                    item[0],
                ),
                reverse=True,
            )
        ]
        return ProjectionRebuildHistory(
            rebuilds=ordered,
            total_count=len(ordered),
        )

    def projection_statuses(self) -> list[ProjectionLifecycleStatus]:
        latest_by_name: dict[str, ProjectionRebuildRecord] = {}
        for record in self.rebuild_history().rebuilds:
            latest_by_name.setdefault(record.projection_name, record)

        return [
            self._status_for_schema(
                schema,
                latest_by_name.get(schema.projection_type),
            )
            for schema in self._registry.list_schemas()
        ]

    def _register_terminal(
        self,
        handle: ProjectionRebuildHandle,
        *,
        status: Literal["completed", "failed"],
        event_type: EventType,
        severity: Severity,
        message: str,
        diagnostic_metadata: dict[str, Any],
    ) -> ProjectionRebuildRecord:
        completed_at = self._clock()
        duration_ms = round(
            max(
                0.0,
                (
                    completed_at - handle.record.rebuild_started_at
                ).total_seconds()
                * 1000,
            ),
            3,
        )
        record = handle.record.model_copy(
            update={
                "rebuild_completed_at": completed_at,
                "status": status,
                "duration_ms": duration_ms,
            }
        )
        self._events.emit_event_sync(
            event_type=event_type,
            severity=severity,
            message=message,
            metadata={
                **diagnostic_metadata,
                **record.model_dump(mode="json"),
                "rebuild_start_event_id": handle.start_event_id,
            },
        )
        return record

    def _source_events(self, source: str) -> list[RuntimeEvent]:
        return projection_source_events(
            self._events.list_persisted_events(),
            source,
        )

    def _rebuild_events(self) -> list[RuntimeEvent]:
        return [
            event
            for event in self._events.list_persisted_events()
            if event.type == EventType.PROJECTION_REBUILD_STARTED
            or event.type in TERMINAL_REBUILD_EVENT_TYPES
        ]

    @staticmethod
    def _start_record(event: RuntimeEvent) -> ProjectionRebuildRecord:
        metadata = event.metadata
        projection_name = metadata.get("projection_name")
        if projection_name is None:
            projection_name = metadata["projection_type"]
        projection_version = metadata.get("projection_version")
        if projection_version is None:
            projection_version = metadata["schema_version"]
        return ProjectionRebuildRecord(
            projection_name=projection_name,
            projection_version=projection_version,
            rebuild_started_at=metadata.get(
                "rebuild_started_at",
                event.ts,
            ),
            rebuild_completed_at=metadata.get("rebuild_completed_at"),
            status=metadata.get("status", "started"),
            source_event_count=metadata.get("source_event_count", 0),
            source_event_range_start=metadata.get(
                "source_event_range_start"
            ),
            source_event_range_end=metadata.get("source_event_range_end"),
            duration_ms=metadata.get("duration_ms"),
        )

    @staticmethod
    def _terminal_record(
        event: RuntimeEvent,
        started: ProjectionRebuildRecord,
    ) -> ProjectionRebuildRecord:
        metadata = event.metadata
        completed_at = datetime.fromisoformat(
            metadata.get("rebuild_completed_at", event.ts).replace(
                "Z",
                "+00:00",
            )
        )
        duration_ms = metadata.get("duration_ms")
        if duration_ms is None:
            duration_ms = round(
                max(
                    0.0,
                    (
                        completed_at - started.rebuild_started_at
                    ).total_seconds()
                    * 1000,
                ),
                3,
            )
        return started.model_copy(
            update={
                "rebuild_completed_at": completed_at,
                "status": (
                    "completed"
                    if event.type == EventType.PROJECTION_REBUILD_COMPLETED
                    else "failed"
                ),
                "duration_ms": duration_ms,
            }
        )

    @staticmethod
    def _projection_source_key(event: RuntimeEvent) -> tuple[str, str]:
        return (
            str(
                event.metadata.get(
                    "projection_name",
                    event.metadata.get("projection_type", ""),
                )
            ),
            str(event.metadata.get("source", "")),
        )

    @staticmethod
    def _status_for_schema(
        schema: ProjectionSchemaInfo,
        latest: ProjectionRebuildRecord | None,
    ) -> ProjectionLifecycleStatus:
        return ProjectionLifecycleStatus(
            projection_name=schema.projection_type,
            projection_version=schema.schema_version,
            latest_rebuild_status=latest.status if latest else None,
            latest_rebuild_started_at=(
                latest.rebuild_started_at if latest else None
            ),
            latest_rebuild_completed_at=(
                latest.rebuild_completed_at if latest else None
            ),
            latest_rebuild_duration_ms=(
                latest.duration_ms if latest else None
            ),
        )


projection_lifecycle_service = ProjectionLifecycleService()
