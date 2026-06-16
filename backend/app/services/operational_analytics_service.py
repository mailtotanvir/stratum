from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from time import perf_counter
from typing import Any

from app.models.governance_audit import GovernanceAuditSummary
from app.models.operational_analytics import (
    GovernanceAnalytics,
    ProjectionAnalytics,
    ReconstructionAnalytics,
    RuntimeOperationalAnalytics,
    RuntimeTrendAnalytics,
    RuntimeTrendBucket,
)
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.models.runtime_session import RuntimeSessionStatus
from app.runtime.projection_registry import (
    ProjectionRegistry,
    projection_registry,
)
from app.services.event_service import EventService, event_service
from app.services.governance_audit_service import (
    GovernanceAuditService,
    governance_audit_service,
)
from app.services.runtime_reconstruction_service import (
    RuntimeReconstructionService,
    runtime_reconstruction_service,
)
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)


DEFAULT_TREND_LOOKBACK_DAYS = 7
ANALYTICS_EVENT_TYPES = frozenset(
    {
        EventType.OPERATIONAL_ANALYTICS_GENERATED.value,
        EventType.OPERATIONAL_ANALYTICS_FAILED.value,
    }
)
GOVERNANCE_EVENT_TYPES = frozenset(
    {
        EventType.RUNTIME_GOVERNANCE_WARNING.value,
        EventType.RUNTIME_GOVERNANCE_BLOCKED.value,
        EventType.TOOL_EXECUTION_GOVERNANCE_WARNING.value,
        EventType.TOOL_EXECUTION_GOVERNANCE_BLOCKED.value,
        EventType.GOVERNANCE_PROJECTION_UPDATED.value,
        EventType.GOVERNANCE_DECISION_RECORDED.value,
        EventType.GOVERNANCE_PROJECTION_REBUILT.value,
        EventType.REFLECTION_REQUESTED.value,
        EventType.REFLECTION_RESOLVED.value,
        EventType.PROPOSAL_RESOLVED.value,
    }
)


class OperationalAnalyticsGenerationError(RuntimeError):
    pass


class OperationalAnalyticsService:
    def __init__(
        self,
        events: EventService | None = None,
        sessions: RuntimeSessionService | None = None,
        governance: GovernanceAuditService | None = None,
        projections: ProjectionRegistry | None = None,
        reconstruction: RuntimeReconstructionService | None = None,
        clock: Callable[[], datetime] | None = None,
        timer: Callable[[], float] | None = None,
    ) -> None:
        self._events = events or event_service
        self._sessions = sessions or runtime_session_service
        self._governance = governance or governance_audit_service
        self._projections = projections or projection_registry
        self._reconstruction = reconstruction or runtime_reconstruction_service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._timer = timer or perf_counter
        self._requests_total = 0
        self._failures_total = 0
        self._last_duration_ms = 0.0

    def generate(
        self,
        lookback_days: int = DEFAULT_TREND_LOOKBACK_DAYS,
    ) -> RuntimeOperationalAnalytics:
        started_at = self._start_request()
        try:
            events = self._source_events()
            generated_at = self._clock()
            incomplete_reasons: list[str] = []
            governance = self._safe_section(
                "governance_analytics_unavailable",
                self._governance_analytics,
                incomplete_reasons,
            )
            projections = self._safe_section(
                "projection_analytics_unavailable",
                lambda: self._projection_analytics(events),
                incomplete_reasons,
            )
            reconstruction = self._safe_section(
                "reconstruction_analytics_unavailable",
                lambda: self._reconstruction_analytics(events),
                incomplete_reasons,
            )
            trends = self._safe_section(
                "trend_analytics_unavailable",
                lambda: self._trend_analytics(events, lookback_days),
                incomplete_reasons,
            )
            counts = self._runtime_counts(events)
            analytics = RuntimeOperationalAnalytics(
                generated_at=generated_at,
                **counts,
                governance=governance,
                projections=projections,
                reconstruction=reconstruction,
                trends=trends,
                incomplete=bool(incomplete_reasons),
                incomplete_reasons=sorted(set(incomplete_reasons)),
                metadata={
                    "derived": True,
                    "authoritative_source": "runtime_event_store",
                    "projection_state_mutated": False,
                },
            )
        except Exception as exc:
            self._record_failure(started_at, exc)
            raise OperationalAnalyticsGenerationError(
                f"Operational analytics generation failed: {exc}"
            ) from exc

        self._record_success(started_at, "full")
        return analytics

    def governance(self) -> GovernanceAnalytics:
        started_at = self._start_request()
        try:
            analytics = self._governance_analytics()
        except Exception as exc:
            self._record_failure(started_at, exc)
            raise OperationalAnalyticsGenerationError(
                f"Governance analytics generation failed: {exc}"
            ) from exc
        self._record_success(started_at, "governance")
        return analytics

    def projections(self) -> ProjectionAnalytics:
        started_at = self._start_request()
        try:
            analytics = self._projection_analytics(self._source_events())
        except Exception as exc:
            self._record_failure(started_at, exc)
            raise OperationalAnalyticsGenerationError(
                f"Projection analytics generation failed: {exc}"
            ) from exc
        self._record_success(started_at, "projections")
        return analytics

    def reconstruction(self) -> ReconstructionAnalytics:
        started_at = self._start_request()
        try:
            analytics = self._reconstruction_analytics(self._source_events())
        except Exception as exc:
            self._record_failure(started_at, exc)
            raise OperationalAnalyticsGenerationError(
                f"Reconstruction analytics generation failed: {exc}"
            ) from exc
        self._record_success(started_at, "reconstruction")
        return analytics

    def trends(
        self,
        lookback_days: int = DEFAULT_TREND_LOOKBACK_DAYS,
    ) -> RuntimeTrendAnalytics:
        started_at = self._start_request()
        try:
            analytics = self._trend_analytics(
                self._source_events(),
                lookback_days,
            )
        except Exception as exc:
            self._record_failure(started_at, exc)
            raise OperationalAnalyticsGenerationError(
                f"Trend analytics generation failed: {exc}"
            ) from exc
        self._record_success(started_at, "trends")
        return analytics

    def observability_metrics(self) -> dict[str, float | int]:
        return {
            "analytics_requests_total": self._requests_total,
            "analytics_generation_failures_total": self._failures_total,
            "analytics_generation_duration_ms": self._last_duration_ms,
        }

    def _runtime_counts(
        self,
        events: list[RuntimeEvent],
    ) -> dict[str, int]:
        sessions = self._sessions.list_sessions()
        session_counts = Counter(session.status for session in sessions)
        return {
            "total_sessions": len(sessions),
            "active_sessions": (
                session_counts[RuntimeSessionStatus.CREATED.value]
                + session_counts[RuntimeSessionStatus.RUNNING.value]
            ),
            "completed_sessions": session_counts[
                RuntimeSessionStatus.COMPLETED.value
            ],
            "failed_sessions": (
                session_counts[RuntimeSessionStatus.INTERRUPTED.value]
                + session_counts[RuntimeSessionStatus.STOPPED.value]
            ),
            "total_events": len(events),
            "total_proposals": _event_count(
                events,
                EventType.PROPOSAL_GENERATED,
            ),
            "total_decisions": _event_count(
                events,
                EventType.DECISION_RECORD_CREATED,
            ),
            "total_artifacts": _event_count(
                events,
                EventType.ARTIFACT_CREATED,
            ),
            "total_tool_executions": _event_count(
                events,
                EventType.TOOL_EXECUTION_COMPLETED,
            )
            + _event_count(events, EventType.TOOL_EXECUTION_FAILED),
        }

    def _governance_analytics(self) -> GovernanceAnalytics:
        summary = self._governance.summary()
        if not isinstance(summary, GovernanceAuditSummary):
            raise TypeError("Malformed governance summary")
        total = max(1, summary.governance_records_total)
        governance_actions = (
            summary.approvals
            + summary.rejections
            + summary.policy_evaluations
            + summary.reflection_triggers
            + summary.budget_actions
        )
        return GovernanceAnalytics(
            approvals=summary.approvals,
            rejections=summary.rejections,
            policy_evaluations=summary.policy_evaluations,
            reflection_triggers=summary.reflection_triggers,
            budget_actions=summary.budget_actions,
            governance_activity_rate=round(governance_actions / total, 6),
        )

    def _projection_analytics(
        self,
        events: list[RuntimeEvent],
    ) -> ProjectionAnalytics:
        return ProjectionAnalytics(
            registered_projections=len(self._projections.list_projection_types()),
            projection_rebuilds=_event_count(
                events,
                EventType.PROJECTION_REBUILD_COMPLETED,
            ),
            projection_replays=_event_count(
                events,
                EventType.PROJECTION_REPLAY_COMPLETED,
            )
            + _event_count(
                events,
                EventType.PROJECTION_REPLAY_DRY_RUN_COMPLETED,
            ),
            drift_checks=_event_count(
                events,
                EventType.PROJECTION_DRIFT_CHECK_COMPLETED,
            )
            + _event_count(events, EventType.PROJECTION_DRIFT_DETECTED),
            drift_detections=_event_count(
                events,
                EventType.PROJECTION_DRIFT_DETECTED,
            ),
            projection_failures=sum(
                1
                for event in events
                if event.type
                in {
                    EventType.PROJECTION_REBUILD_FAILED,
                    EventType.PROJECTION_REPLAY_FAILED,
                    EventType.PROJECTION_DRIFT_CHECK_FAILED,
                    EventType.PROJECTION_VERIFICATION_FAILED,
                    EventType.PROJECTION_MANIFEST_GENERATION_FAILED,
                    EventType.PROJECTION_SNAPSHOT_EXPORT_FAILED,
                    EventType.PROJECTION_LINEAGE_GENERATION_FAILED,
                }
            ),
        )

    def _reconstruction_analytics(
        self,
        events: list[RuntimeEvent],
    ) -> ReconstructionAnalytics:
        metrics = self._reconstruction.metrics()
        durations = [
            float(event.metadata["duration_ms"])
            for event in events
            if event.type
            in {
                EventType.RUNTIME_RECONSTRUCTION_VIEW_BUILT,
                EventType.RUNTIME_RECONSTRUCTION_VIEW_INCOMPLETE,
            }
            and isinstance(event.metadata.get("duration_ms"), int | float)
        ]
        average = round(sum(durations) / len(durations), 3) if durations else 0.0
        return ReconstructionAnalytics(
            reconstructed_sessions=metrics.reconstructed_sessions_total,
            reconstruction_failures=metrics.reconstruction_failed_views_total,
            incomplete_reconstructions=(
                metrics.reconstruction_incomplete_views_total
            ),
            average_reconstruction_duration_ms=average,
        )

    def _trend_analytics(
        self,
        events: list[RuntimeEvent],
        lookback_days: int,
    ) -> RuntimeTrendAnalytics:
        if lookback_days < 1:
            raise ValueError("lookback_days must be greater than or equal to 1")
        today = self._clock().date()
        first_day = today - timedelta(days=lookback_days - 1)
        buckets: dict[date, Counter[str]] = {
            first_day + timedelta(days=offset): Counter()
            for offset in range(lookback_days)
        }
        for event in events:
            day = _event_date(event)
            if day is None or day not in buckets:
                continue
            buckets[day]["events"] += 1
            if event.type == EventType.DECISION_RECORD_CREATED:
                buckets[day]["decisions"] += 1
            if event.type == EventType.ARTIFACT_CREATED:
                buckets[day]["artifacts"] += 1
            if event.type.value in GOVERNANCE_EVENT_TYPES:
                buckets[day]["governance_actions"] += 1

        ordered = [
            RuntimeTrendBucket(
                day=day,
                events=buckets[day]["events"],
                decisions=buckets[day]["decisions"],
                artifacts=buckets[day]["artifacts"],
                governance_actions=buckets[day]["governance_actions"],
            )
            for day in sorted(buckets)
        ]
        return RuntimeTrendAnalytics(
            lookback_days=lookback_days,
            buckets=ordered,
            events_per_day={
                bucket.day.isoformat(): bucket.events for bucket in ordered
            },
            decisions_per_day={
                bucket.day.isoformat(): bucket.decisions for bucket in ordered
            },
            artifacts_per_day={
                bucket.day.isoformat(): bucket.artifacts for bucket in ordered
            },
            governance_actions_per_day={
                bucket.day.isoformat(): bucket.governance_actions
                for bucket in ordered
            },
        )

    def _safe_section(
        self,
        reason: str,
        build: Callable[[], Any],
        incomplete_reasons: list[str],
    ) -> Any:
        try:
            return build()
        except Exception:
            incomplete_reasons.append(reason)
            if reason == "governance_analytics_unavailable":
                return GovernanceAnalytics(
                    approvals=0,
                    rejections=0,
                    policy_evaluations=0,
                    reflection_triggers=0,
                    budget_actions=0,
                    governance_activity_rate=0,
                )
            if reason == "projection_analytics_unavailable":
                return ProjectionAnalytics(
                    registered_projections=0,
                    projection_rebuilds=0,
                    projection_replays=0,
                    drift_checks=0,
                    drift_detections=0,
                    projection_failures=0,
                )
            if reason == "reconstruction_analytics_unavailable":
                return ReconstructionAnalytics(
                    reconstructed_sessions=0,
                    reconstruction_failures=0,
                    incomplete_reconstructions=0,
                    average_reconstruction_duration_ms=0,
                )
            return RuntimeTrendAnalytics(
                lookback_days=DEFAULT_TREND_LOOKBACK_DAYS,
                buckets=[],
                events_per_day={},
                decisions_per_day={},
                artifacts_per_day={},
                governance_actions_per_day={},
            )

    def _source_events(self) -> list[RuntimeEvent]:
        return [
            event
            for event in self._events.list_persisted_events()
            if event.type.value not in ANALYTICS_EVENT_TYPES
        ]

    def _start_request(self) -> float:
        self._requests_total += 1
        return self._timer()

    def _record_success(self, started_at: float, view: str) -> None:
        duration_ms = self._duration_ms(started_at)
        self._last_duration_ms = duration_ms
        self._events.emit_event_sync(
            event_type=EventType.OPERATIONAL_ANALYTICS_GENERATED,
            message="Operational analytics generated",
            metadata={
                "view": view,
                **self.observability_metrics(),
            },
        )

    def _record_failure(self, started_at: float, exc: Exception) -> None:
        self._failures_total += 1
        duration_ms = self._duration_ms(started_at)
        self._last_duration_ms = duration_ms
        self._events.emit_event_sync(
            event_type=EventType.OPERATIONAL_ANALYTICS_FAILED,
            severity=Severity.ERROR,
            message=f"Operational analytics failed: {exc}",
            metadata={
                "error_type": type(exc).__name__,
                **self.observability_metrics(),
            },
        )

    def _duration_ms(self, started_at: float) -> float:
        return round(max(0.0, (self._timer() - started_at) * 1000), 3)


def _event_count(events: list[RuntimeEvent], event_type: EventType) -> int:
    return sum(1 for event in events if event.type == event_type)


def _event_date(event: RuntimeEvent) -> date | None:
    try:
        return datetime.fromisoformat(event.ts.replace("Z", "+00:00")).date()
    except ValueError:
        return None


operational_analytics_service = OperationalAnalyticsService()
