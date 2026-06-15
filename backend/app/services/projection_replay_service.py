from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.models.projection_replay import (
    ProjectionReplayRequest,
    ProjectionReplayResult,
    ProjectionReplayStatus,
)
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.runtime.projection_registry import (
    ProjectionRegistry,
    projection_registry,
)
from app.services.event_service import EventService, event_service
from app.services.projection_fingerprint import projection_state_fingerprint
from app.services.projection_snapshot_manifest_service import (
    NON_SOURCE_EVENT_TYPES,
)


DECISION_REPLAY_EVENT_TYPES = frozenset(
    {
        EventType.PLANNER_RECOMMENDATION_CREATED,
        EventType.PLANNER_RECOMMENDATION_PROMOTED,
        EventType.PLANNER_RECOMMENDATION_DISMISSED,
        EventType.DECISION_RECORD_CREATED,
        EventType.DECISION_EVIDENCE_CREATED,
        EventType.PROPOSAL_GENERATED,
        EventType.PROPOSAL_RESOLVED,
    }
)

DECISION_LINEAGE_REPLAY_EVENT_TYPES = frozenset(
    {
        *DECISION_REPLAY_EVENT_TYPES,
        EventType.PROPOSAL_ARTIFACT_ATTACHED,
        EventType.ARTIFACT_CREATED,
    }
)

ARTIFACT_LINEAGE_REPLAY_EVENT_TYPES = frozenset(
    {
        EventType.ARTIFACT_CREATED,
        EventType.RUNTIME_ARTIFACT_ATTACHED,
        EventType.PROPOSAL_ARTIFACT_ATTACHED,
        EventType.TOOL_INVOCATION_REQUESTED,
        EventType.TOOL_INVOCATION_RUNNING,
        EventType.TOOL_INVOCATION_COMPLETED,
        EventType.TOOL_INVOCATION_FAILED,
        EventType.TOOL_EXECUTION_STARTED,
        EventType.TOOL_EXECUTION_COMPLETED,
        EventType.TOOL_EXECUTION_FAILED,
        EventType.PROPOSAL_GENERATED,
        EventType.PROPOSAL_RESOLVED,
        EventType.DECISION_RECORD_CREATED,
    }
)


@dataclass(frozen=True)
class ProjectionReplaySnapshot:
    state: dict[str, Any]
    source_event_count: int
    applied_event_count: int
    skipped_event_count: int

    @property
    def fingerprint(self) -> str:
        return projection_state_fingerprint(self.state)


class ProjectionReplayAdapter(Protocol):
    def accepts(self, event: RuntimeEvent) -> bool:
        """Return whether this event contributes to the projection."""

    def apply(
        self,
        state: dict[str, Any],
        event: RuntimeEvent,
    ) -> None:
        """Apply one event to request-scoped replay state."""


class EventTypeProjectionReplayAdapter:
    def __init__(self, event_types: frozenset[EventType]) -> None:
        self._event_types = event_types

    def accepts(self, event: RuntimeEvent) -> bool:
        return event.type in self._event_types

    def apply(
        self,
        state: dict[str, Any],
        event: RuntimeEvent,
    ) -> None:
        applied_event_ids = state.setdefault("applied_event_ids", [])
        applied_event_ids.append(event.id)
        applied_events = state.setdefault("applied_events", [])
        applied_events.append(
            {
                "id": event.id,
                "type": event.type.value,
                "severity": event.severity.value,
                "message": event.message,
                "metadata": deepcopy(event.metadata),
            }
        )
        event_type_counts = state.setdefault("event_type_counts", {})
        event_type = event.type.value
        event_type_counts[event_type] = (
            event_type_counts.get(event_type, 0) + 1
        )


class AllEventsProjectionReplayAdapter(EventTypeProjectionReplayAdapter):
    def __init__(self) -> None:
        super().__init__(frozenset())

    def accepts(self, event: RuntimeEvent) -> bool:
        return True


class ProjectionReplayError(RuntimeError):
    def __init__(
        self,
        message: str,
        result: ProjectionReplayResult,
    ) -> None:
        super().__init__(message)
        self.result = result


class ProjectionReplayService:
    def __init__(
        self,
        registry: ProjectionRegistry | None = None,
        events: EventService | None = None,
        adapters: dict[str, ProjectionReplayAdapter] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._registry = registry or projection_registry
        self._events = events or event_service
        self._adapters = (
            adapters
            if adapters is not None
            else {
                "artifact_lineage_projection": (
                    EventTypeProjectionReplayAdapter(
                        ARTIFACT_LINEAGE_REPLAY_EVENT_TYPES
                    )
                ),
                "decision_lineage_projection": (
                    EventTypeProjectionReplayAdapter(
                        DECISION_LINEAGE_REPLAY_EVENT_TYPES
                    )
                ),
                "decision_projection": EventTypeProjectionReplayAdapter(
                    DECISION_REPLAY_EVENT_TYPES
                ),
                "session_decision_projection": (
                    EventTypeProjectionReplayAdapter(
                        DECISION_REPLAY_EVENT_TYPES
                    )
                ),
            }
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    def preview(
        self,
        request: ProjectionReplayRequest,
    ) -> ProjectionReplayResult:
        return self._replay(request, dry_run=True)

    def replay(
        self,
        request: ProjectionReplayRequest,
    ) -> ProjectionReplayResult:
        return self._replay(request, dry_run=False)

    def derive_snapshot(
        self,
        request: ProjectionReplayRequest,
    ) -> ProjectionReplaySnapshot:
        self._registry.get_schema(request.projection_name)
        adapter = self._adapter_for(request.projection_name)
        source_events = self._source_events(request)
        state: dict[str, Any] = {}
        applied = 0
        skipped = 0
        for event in source_events:
            if not adapter.accepts(event):
                skipped += 1
                continue
            adapter.apply(state, event)
            applied += 1
        return ProjectionReplaySnapshot(
            state=deepcopy(state),
            source_event_count=len(source_events),
            applied_event_count=applied,
            skipped_event_count=skipped,
        )

    def _replay(
        self,
        request: ProjectionReplayRequest,
        *,
        dry_run: bool,
    ) -> ProjectionReplayResult:
        schema = self._registry.get_schema(request.projection_name)
        adapter = self._adapter_for(request.projection_name)
        source_events = self._source_events(request)
        started_at = self._clock()
        self._emit(
            EventType.PROJECTION_REPLAY_STARTED,
            schema.projection_type,
            schema.schema_version,
            dry_run=dry_run,
            source_event_count=len(source_events),
            applied_event_count=0,
            skipped_event_count=0,
            failed_event_count=0,
        )

        state: dict[str, Any] = {}
        applied = 0
        skipped = 0
        failed = 0
        try:
            for event in source_events:
                if not adapter.accepts(event):
                    skipped += 1
                    continue
                adapter.apply(state, event)
                applied += 1
            if not dry_run:
                state = self._complete_replay_state(state)
        except Exception as exc:
            failed += 1
            completed_at = self._clock()
            result = self._result(
                request,
                schema.schema_version,
                started_at,
                completed_at,
                status="failed",
                source_event_count=len(source_events),
                applied_event_count=applied,
                skipped_event_count=skipped,
                failed_event_count=failed,
                dry_run=dry_run,
            )
            self._emit_result(
                EventType.PROJECTION_REPLAY_FAILED,
                result,
                severity=Severity.ERROR,
                error_type=type(exc).__name__,
            )
            raise ProjectionReplayError(
                f"Projection replay failed: {exc}",
                result,
            ) from exc

        completed_at = self._clock()
        result = self._result(
            request,
            schema.schema_version,
            started_at,
            completed_at,
            status="completed",
            source_event_count=len(source_events),
            applied_event_count=applied,
            skipped_event_count=skipped,
            failed_event_count=failed,
            dry_run=dry_run,
        )
        self._emit_result(
            (
                EventType.PROJECTION_REPLAY_DRY_RUN_COMPLETED
                if dry_run
                else EventType.PROJECTION_REPLAY_COMPLETED
            ),
            result,
            projection_fingerprint=projection_state_fingerprint(state),
        )
        return result

    def _source_events(
        self,
        request: ProjectionReplayRequest,
    ) -> list[RuntimeEvent]:
        events = [
            event
            for event in self._events.list_persisted_events()
            if event.type.value not in NON_SOURCE_EVENT_TYPES
            and (
                request.event_id_start is None
                or event.id >= request.event_id_start
            )
            and (
                request.event_id_end is None
                or event.id <= request.event_id_end
            )
        ]
        return sorted(
            events,
            key=lambda event: (event.id, event.ts, event.type.value),
        )

    def _adapter_for(
        self,
        projection_name: str,
    ) -> ProjectionReplayAdapter:
        return self._adapters.get(
            projection_name,
            AllEventsProjectionReplayAdapter(),
        )

    @staticmethod
    def _complete_replay_state(state: dict[str, Any]) -> dict[str, Any]:
        # Replay state is deliberately request-scoped and never persisted.
        return deepcopy(state)

    @staticmethod
    def _result(
        request: ProjectionReplayRequest,
        projection_version: int,
        started_at: datetime,
        completed_at: datetime,
        *,
        status: ProjectionReplayStatus,
        source_event_count: int,
        applied_event_count: int,
        skipped_event_count: int,
        failed_event_count: int,
        dry_run: bool,
    ) -> ProjectionReplayResult:
        return ProjectionReplayResult(
            projection_name=request.projection_name,
            projection_version=projection_version,
            replay_started_at=started_at,
            replay_completed_at=completed_at,
            status=status,
            source_event_count=source_event_count,
            applied_event_count=applied_event_count,
            skipped_event_count=skipped_event_count,
            failed_event_count=failed_event_count,
            duration_ms=round(
                max(
                    0.0,
                    (completed_at - started_at).total_seconds() * 1000,
                ),
                3,
            ),
            dry_run=dry_run,
        )

    def _emit_result(
        self,
        event_type: EventType,
        result: ProjectionReplayResult,
        *,
        severity: Severity = Severity.INFO,
        **extra: Any,
    ) -> None:
        self._emit(
            event_type,
            result.projection_name,
            result.projection_version,
            severity=severity,
            dry_run=result.dry_run,
            source_event_count=result.source_event_count,
            applied_event_count=result.applied_event_count,
            skipped_event_count=result.skipped_event_count,
            failed_event_count=result.failed_event_count,
            duration_ms=result.duration_ms,
            status=result.status,
            **extra,
        )

    def _emit(
        self,
        event_type: EventType,
        projection_name: str,
        projection_version: int,
        *,
        severity: Severity = Severity.INFO,
        **metadata: Any,
    ) -> None:
        self._events.emit_event_sync(
            event_type=event_type,
            severity=severity,
            message=event_type.value.replace("_", " ").capitalize(),
            metadata={
                "projection_name": projection_name,
                "projection_version": projection_version,
                **metadata,
            },
        )


projection_replay_service = ProjectionReplayService()
