from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.models.projection_drift import (
    ProjectionDriftReport,
    ProjectionDriftResult,
    ProjectionDriftStatus,
)
from app.models.projection_replay import ProjectionReplayRequest
from app.models.runtime_event import EventType, Severity
from app.runtime.projection_registry import (
    ProjectionRegistry,
    projection_registry,
)
from app.runtime.projection_visibility import (
    PUBLIC_RUNTIME_PROJECTION_TYPES,
)
from app.services.event_service import EventService, event_service
from app.services.projection_replay_service import (
    ProjectionReplayService,
    projection_replay_service,
)


class ProjectionDriftCheckError(RuntimeError):
    def __init__(
        self,
        message: str,
        result: ProjectionDriftResult,
    ) -> None:
        super().__init__(message)
        self.result = result


class ProjectionDriftService:
    def __init__(
        self,
        registry: ProjectionRegistry | None = None,
        events: EventService | None = None,
        replay: ProjectionReplayService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._registry = registry or projection_registry
        self._events = events or event_service
        self._replay = replay or projection_replay_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def check_all(self) -> ProjectionDriftReport:
        results: list[ProjectionDriftResult] = []
        for projection_name in PUBLIC_RUNTIME_PROJECTION_TYPES:
            if projection_name not in self._registry.list_projection_types():
                continue
            try:
                results.append(self.check_projection(projection_name))
            except ProjectionDriftCheckError as exc:
                results.append(exc.result)
        return ProjectionDriftReport(
            projections=results,
            projection_count=len(results),
            drifted_count=sum(
                result.status == "drifted" for result in results
            ),
            unavailable_count=sum(
                result.status == "unavailable" for result in results
            ),
            failed_count=sum(
                result.status == "failed" for result in results
            ),
        )

    def check_projection(
        self,
        projection_name: str,
    ) -> ProjectionDriftResult:
        schema = self._registry.get_schema(projection_name)
        started_at = self._clock()
        self._emit(
            EventType.PROJECTION_DRIFT_CHECK_STARTED,
            projection_name,
            schema.schema_version,
        )
        persisted_fingerprint = self._persisted_fingerprint(
            projection_name
        )
        try:
            replay_snapshot = self._replay.derive_snapshot(
                ProjectionReplayRequest(
                    projection_name=projection_name,
                )
            )
            replay_fingerprint = replay_snapshot.fingerprint
        except Exception as exc:
            checked_at = self._clock()
            result = self._result(
                projection_name=projection_name,
                projection_version=schema.schema_version,
                started_at=started_at,
                checked_at=checked_at,
                status="failed",
                drift_detected=False,
                source_event_count=0,
                persisted_fingerprint=persisted_fingerprint,
                replay_fingerprint=None,
                mismatch_summary=[
                    f"Replay-derived state unavailable: {exc}"
                ],
            )
            self._emit_result(
                EventType.PROJECTION_DRIFT_CHECK_FAILED,
                result,
                severity=Severity.ERROR,
                error_type=type(exc).__name__,
            )
            raise ProjectionDriftCheckError(
                f"Projection drift check failed: {exc}",
                result,
            ) from exc

        checked_at = self._clock()
        if persisted_fingerprint is None:
            status = "unavailable"
            drift_detected = False
            mismatch_summary = [
                "No successful projection replay baseline is available"
            ]
        elif persisted_fingerprint == replay_fingerprint:
            status = "in_sync"
            drift_detected = False
            mismatch_summary = []
        else:
            status = "drifted"
            drift_detected = True
            mismatch_summary = [
                "Persisted projection fingerprint differs from "
                "replay-derived fingerprint"
            ]

        result = self._result(
            projection_name=projection_name,
            projection_version=schema.schema_version,
            started_at=started_at,
            checked_at=checked_at,
            status=status,
            drift_detected=drift_detected,
            source_event_count=replay_snapshot.source_event_count,
            persisted_fingerprint=persisted_fingerprint,
            replay_fingerprint=replay_fingerprint,
            mismatch_summary=mismatch_summary,
        )
        self._emit_result(
            (
                EventType.PROJECTION_DRIFT_DETECTED
                if drift_detected
                else EventType.PROJECTION_DRIFT_CHECK_COMPLETED
            ),
            result,
            severity=(
                Severity.WARNING if drift_detected else Severity.INFO
            ),
        )
        return result

    def _persisted_fingerprint(
        self,
        projection_name: str,
    ) -> str | None:
        events = self._events.list_persisted_events(
            event_type=EventType.PROJECTION_REPLAY_COMPLETED.value
        )
        for event in reversed(events):
            if event.metadata.get("projection_name") != projection_name:
                continue
            fingerprint = event.metadata.get("projection_fingerprint")
            if isinstance(fingerprint, str):
                return fingerprint
        return None

    @staticmethod
    def _result(
        *,
        projection_name: str,
        projection_version: int,
        started_at: datetime,
        checked_at: datetime,
        status: ProjectionDriftStatus,
        drift_detected: bool,
        source_event_count: int,
        persisted_fingerprint: str | None,
        replay_fingerprint: str | None,
        mismatch_summary: list[str],
    ) -> ProjectionDriftResult:
        return ProjectionDriftResult(
            projection_name=projection_name,
            projection_version=projection_version,
            checked_at=checked_at,
            status=status,
            drift_detected=drift_detected,
            source_event_count=source_event_count,
            persisted_projection_fingerprint=persisted_fingerprint,
            replay_projection_fingerprint=replay_fingerprint,
            mismatch_summary=mismatch_summary,
            duration_ms=round(
                max(
                    0.0,
                    (checked_at - started_at).total_seconds() * 1000,
                ),
                3,
            ),
        )

    def _emit_result(
        self,
        event_type: EventType,
        result: ProjectionDriftResult,
        *,
        severity: Severity = Severity.INFO,
        **extra: Any,
    ) -> None:
        self._emit(
            event_type,
            result.projection_name,
            result.projection_version,
            severity=severity,
            status=result.status,
            drift_detected=result.drift_detected,
            source_event_count=result.source_event_count,
            duration_ms=result.duration_ms,
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


projection_drift_service = ProjectionDriftService()
