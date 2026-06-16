from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

from app.models.operational_analytics import (
    GovernanceAnalytics,
    ProjectionAnalytics,
    ReconstructionAnalytics,
    RuntimeOperationalAnalytics,
    RuntimeTrendAnalytics,
)
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.models.runtime_health import RuntimeHealthStatus
from app.models.runtime_intelligence import (
    RuntimeActivityItem,
    RuntimeActivitySummary,
    RuntimeGovernanceIntelligenceSummary,
    RuntimeIntegritySummary,
    RuntimeIntelligenceStatus,
    RuntimeIntelligenceSummary,
    RuntimeRisk,
    RuntimeRiskLevel,
    RuntimeRiskSeverity,
    RuntimeRiskSummary,
)
from app.models.runtime_reconstruction import RuntimeReconstructionMetrics
from app.services.event_service import EventService, event_service
from app.services.operational_analytics_service import (
    DEFAULT_TREND_LOOKBACK_DAYS,
    OperationalAnalyticsService,
    operational_analytics_service,
)
from app.services.projection_lifecycle_service import (
    ProjectionLifecycleService,
    projection_lifecycle_service,
)
from app.services.runtime_health_service import (
    RuntimeHealthService,
    runtime_health_service,
)
from app.services.runtime_reconstruction_service import (
    RuntimeReconstructionService,
    runtime_reconstruction_service,
)


DEFAULT_ACTIVITY_LIMIT = 10
STALE_PROJECTION_REBUILD_DAYS = 7
INTELLIGENCE_EVENT_TYPES = frozenset(
    {
        EventType.RUNTIME_INTELLIGENCE_GENERATED.value,
        EventType.RUNTIME_INTELLIGENCE_FAILED.value,
        EventType.RUNTIME_RISK_DETECTED.value,
    }
)
HIGH_SIGNAL_EVENT_TYPES = frozenset(
    {
        EventType.RUNTIME_GOVERNANCE_WARNING.value,
        EventType.RUNTIME_GOVERNANCE_BLOCKED.value,
        EventType.TOOL_EXECUTION_GOVERNANCE_WARNING.value,
        EventType.TOOL_EXECUTION_GOVERNANCE_BLOCKED.value,
        EventType.PROJECTION_DRIFT_DETECTED.value,
        EventType.PROJECTION_REBUILD_FAILED.value,
        EventType.PROJECTION_REPLAY_FAILED.value,
        EventType.PROJECTION_DRIFT_CHECK_FAILED.value,
        EventType.RUNTIME_RECONSTRUCTION_VIEW_INCOMPLETE.value,
        EventType.RUNTIME_RECONSTRUCTION_VIEW_FAILED.value,
        EventType.DECISION_LINEAGE_INCOMPLETE.value,
        EventType.DECISION_LINEAGE_RECONSTRUCTION_FAILED.value,
        EventType.ARTIFACT_LINEAGE_INCOMPLETE.value,
        EventType.ARTIFACT_LINEAGE_RECONSTRUCTION_FAILED.value,
        EventType.ERROR.value,
        EventType.WARNING.value,
    }
)


class RuntimeIntelligenceGenerationError(RuntimeError):
    pass


class RuntimeIntelligenceService:
    def __init__(
        self,
        events: EventService | None = None,
        analytics: OperationalAnalyticsService | None = None,
        health: RuntimeHealthService | None = None,
        lifecycle: ProjectionLifecycleService | None = None,
        reconstruction: RuntimeReconstructionService | None = None,
        clock: Callable[[], datetime] | None = None,
        timer: Callable[[], float] | None = None,
    ) -> None:
        self._events = events or event_service
        self._analytics = analytics or operational_analytics_service
        self._health = health or runtime_health_service
        self._lifecycle = lifecycle or projection_lifecycle_service
        self._reconstruction = reconstruction or runtime_reconstruction_service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._timer = timer or perf_counter
        self._requests_total = 0
        self._failures_total = 0
        self._risks_detected_total = 0

    def generate(self) -> RuntimeIntelligenceSummary:
        started_at = self._start_request()
        try:
            generated_at = self._clock()
            incomplete_reasons: list[str] = []
            analytics = self._safe_analytics(incomplete_reasons)
            health = self._safe_health(incomplete_reasons)
            events = self._source_events()
            integrity = self._integrity_summary(
                generated_at,
                analytics,
                events,
                incomplete_reasons,
            )
            governance = self._governance_summary(generated_at, analytics)
            risk_summary = self._risk_summary(
                generated_at,
                analytics,
                health,
                integrity,
                governance,
                events,
            )
            activity = self._activity_summary(generated_at, events)
            overall = _worst_status(
                [
                    _status_from_health(health),
                    integrity.projection_integrity_status,
                    integrity.reconstruction_status,
                    governance.governance_status,
                ]
            )
            summary = RuntimeIntelligenceSummary(
                generated_at=generated_at,
                overall_status=overall,
                health_status=_status_from_health(health),
                projection_integrity_status=(
                    integrity.projection_integrity_status
                ),
                governance_status=governance.governance_status,
                reconstruction_status=integrity.reconstruction_status,
                risk_level=risk_summary.risk_level,
                notable_risks=risk_summary.notable_risks,
                recent_activity=activity.recent_activity,
                recommended_operator_attention=(
                    risk_summary.recommended_operator_attention
                    + governance.recommended_operator_attention
                ),
                risk_summary=risk_summary,
                activity_summary=activity,
                integrity_summary=integrity,
                governance_summary=governance,
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
            raise RuntimeIntelligenceGenerationError(
                f"Runtime intelligence generation failed: {exc}"
            ) from exc

        self._record_success(started_at, "full", summary.notable_risks)
        return summary

    def risks(self) -> RuntimeRiskSummary:
        started_at = self._start_request()
        try:
            generated_at = self._clock()
            analytics = self._analytics.generate()
            health = self._health.evaluate()
            events = self._source_events()
            integrity = self._integrity_summary(
                generated_at,
                analytics,
                events,
                [],
            )
            governance = self._governance_summary(generated_at, analytics)
            summary = self._risk_summary(
                generated_at,
                analytics,
                health,
                integrity,
                governance,
                events,
            )
        except Exception as exc:
            self._record_failure(started_at, exc)
            raise RuntimeIntelligenceGenerationError(
                f"Runtime risk summary generation failed: {exc}"
            ) from exc

        self._record_success(started_at, "risks", summary.notable_risks)
        return summary

    def activity(self) -> RuntimeActivitySummary:
        started_at = self._start_request()
        try:
            summary = self._activity_summary(self._clock(), self._source_events())
        except Exception as exc:
            self._record_failure(started_at, exc)
            raise RuntimeIntelligenceGenerationError(
                f"Runtime activity summary generation failed: {exc}"
            ) from exc
        self._record_success(started_at, "activity", [])
        return summary

    def integrity(self) -> RuntimeIntegritySummary:
        started_at = self._start_request()
        try:
            analytics = self._analytics.generate()
            events = self._source_events()
            summary = self._integrity_summary(
                self._clock(),
                analytics,
                events,
                [],
            )
        except Exception as exc:
            self._record_failure(started_at, exc)
            raise RuntimeIntelligenceGenerationError(
                f"Runtime integrity summary generation failed: {exc}"
            ) from exc
        self._record_success(started_at, "integrity", [])
        return summary

    def governance(self) -> RuntimeGovernanceIntelligenceSummary:
        started_at = self._start_request()
        try:
            summary = self._governance_summary(
                self._clock(),
                self._analytics.generate(),
            )
        except Exception as exc:
            self._record_failure(started_at, exc)
            raise RuntimeIntelligenceGenerationError(
                f"Runtime governance intelligence generation failed: {exc}"
            ) from exc
        self._record_success(started_at, "governance", [])
        return summary

    def observability_metrics(self) -> dict[str, int]:
        return {
            "intelligence_requests_total": self._requests_total,
            "intelligence_generation_failures_total": self._failures_total,
            "runtime_risks_detected_total": self._risks_detected_total,
        }

    def _integrity_summary(
        self,
        generated_at: datetime,
        analytics: RuntimeOperationalAnalytics,
        events: list[RuntimeEvent],
        incomplete_reasons: list[str],
    ) -> RuntimeIntegritySummary:
        failed_rebuilds = _event_count(events, EventType.PROJECTION_REBUILD_FAILED)
        failed_replays = _event_count(events, EventType.PROJECTION_REPLAY_FAILED)
        incomplete_lineage = sum(
            1
            for event in events
            if event.type
            in {
                EventType.DECISION_LINEAGE_INCOMPLETE,
                EventType.ARTIFACT_LINEAGE_INCOMPLETE,
            }
        )
        try:
            stale_count = self._stale_projection_rebuild_count(generated_at)
        except Exception:
            incomplete_reasons.append("projection_lifecycle_unavailable")
            stale_count = 0
        try:
            reconstruction_metrics = self._reconstruction.metrics()
        except Exception:
            incomplete_reasons.append("reconstruction_data_unavailable")
            reconstruction_metrics = RuntimeReconstructionMetrics(
                reconstruction_views_built_total=0,
                reconstruction_incomplete_views_total=(
                    analytics.reconstruction.incomplete_reconstructions
                ),
                reconstruction_failed_views_total=(
                    analytics.reconstruction.reconstruction_failures
                ),
                reconstructed_sessions_total=(
                    analytics.reconstruction.reconstructed_sessions
                ),
            )
        incomplete_count = (
            incomplete_lineage
            + analytics.reconstruction.incomplete_reconstructions
            + reconstruction_metrics.reconstruction_incomplete_views_total
        )
        projection_status = _status_for_projection_integrity(
            analytics.projections.drift_detections,
            analytics.projections.projection_failures,
            stale_count,
        )
        reconstruction_status = _status_for_reconstruction_integrity(
            analytics.reconstruction.reconstruction_failures,
            incomplete_count,
        )
        return RuntimeIntegritySummary(
            generated_at=generated_at,
            projection_integrity_status=projection_status,
            reconstruction_status=reconstruction_status,
            drift_detections=analytics.projections.drift_detections,
            projection_failures=analytics.projections.projection_failures,
            failed_rebuilds=failed_rebuilds,
            failed_replays=failed_replays,
            stale_projection_rebuilds=stale_count,
            incomplete_lineage_or_reconstructions=incomplete_count,
            reconstruction_failures=(
                analytics.reconstruction.reconstruction_failures
            ),
            metadata={
                "derived": True,
                "stale_rebuild_threshold_days": STALE_PROJECTION_REBUILD_DAYS,
            },
        )

    def _governance_summary(
        self,
        generated_at: datetime,
        analytics: RuntimeOperationalAnalytics,
    ) -> RuntimeGovernanceIntelligenceSummary:
        approvals = analytics.governance.approvals
        rejections = analytics.governance.rejections
        total = approvals + rejections
        rejection_rate = round(rejections / total, 6) if total else 0.0
        spike = rejections >= 3 and rejection_rate >= 0.5
        status: RuntimeIntelligenceStatus
        if spike:
            status = "degraded"
        elif rejections > 0:
            status = "warning"
        else:
            status = "healthy"
        attention = (
            ["review_governance_rejections"]
            if spike
            else []
        )
        return RuntimeGovernanceIntelligenceSummary(
            generated_at=generated_at,
            governance_status=status,
            approvals=approvals,
            rejections=rejections,
            rejection_rate=rejection_rate,
            governance_activity_rate=analytics.governance.governance_activity_rate,
            rejection_spike_detected=spike,
            recommended_operator_attention=attention,
        )

    def _risk_summary(
        self,
        generated_at: datetime,
        analytics: RuntimeOperationalAnalytics,
        health: RuntimeHealthStatus,
        integrity: RuntimeIntegritySummary,
        governance: RuntimeGovernanceIntelligenceSummary,
        events: list[RuntimeEvent],
    ) -> RuntimeRiskSummary:
        risks: list[RuntimeRisk] = []
        critical_health_count = sum(
            1
            for finding in health.findings
            if finding.severity == "critical"
        ) + sum(1 for event in events if event.severity == Severity.CRITICAL)
        if health.overall_status == "unhealthy" or critical_health_count:
            risks.append(
                _risk(
                    "critical_runtime_health",
                    "critical",
                    "runtime_health",
                    "Critical runtime health issue detected",
                    max(1, critical_health_count),
                )
            )
        if analytics.projections.drift_detections:
            risks.append(
                _risk(
                    "projection_drift_detected",
                    "high",
                    "projection_drift",
                    "Projection drift has been detected",
                    analytics.projections.drift_detections,
                )
            )
        if analytics.reconstruction.reconstruction_failures:
            risks.append(
                _risk(
                    "reconstruction_failures",
                    "high",
                    "runtime_reconstruction",
                    "Runtime reconstruction failures are present",
                    analytics.reconstruction.reconstruction_failures,
                )
            )
        if integrity.failed_replays:
            risks.append(
                _risk(
                    "projection_replay_failures",
                    "high",
                    "projection_replay",
                    "Projection replay failures are present",
                    integrity.failed_replays,
                )
            )
        if integrity.failed_rebuilds:
            risks.append(
                _risk(
                    "projection_rebuild_failures",
                    "high",
                    "projection_rebuild",
                    "Projection rebuild failures are present",
                    integrity.failed_rebuilds,
                )
            )
        if governance.rejection_spike_detected:
            risks.append(
                _risk(
                    "governance_rejection_spike",
                    "high",
                    "governance",
                    "Governance rejection spike detected",
                    governance.rejections,
                )
            )
        if integrity.incomplete_lineage_or_reconstructions:
            risks.append(
                _risk(
                    "incomplete_lineage_or_reconstruction",
                    "moderate",
                    "runtime_reconstruction",
                    "Incomplete lineage or reconstruction evidence is present",
                    integrity.incomplete_lineage_or_reconstructions,
                )
            )
        if integrity.stale_projection_rebuilds:
            risks.append(
                _risk(
                    "stale_projection_rebuilds",
                    "moderate",
                    "projection_lifecycle",
                    "Projection rebuilds are stale or missing",
                    integrity.stale_projection_rebuilds,
                )
            )
        risks = sorted(
            risks,
            key=lambda item: (
                _risk_severity_rank(item.severity),
                item.risk_id,
            ),
        )
        attention = [
            _operator_attention_for(risk.risk_id)
            for risk in risks
        ]
        return RuntimeRiskSummary(
            generated_at=generated_at,
            risk_level=_risk_level(risks),
            notable_risks=risks,
            risk_count=len(risks),
            recommended_operator_attention=sorted(set(attention)),
            metadata={"derived": True},
        )

    def _activity_summary(
        self,
        generated_at: datetime,
        events: list[RuntimeEvent],
    ) -> RuntimeActivitySummary:
        high_signal = [
            event
            for event in events
            if (
                event.type.value in HIGH_SIGNAL_EVENT_TYPES
                or event.severity
                in {Severity.WARNING, Severity.ERROR, Severity.CRITICAL}
            )
            and _event_datetime(event) is not None
        ]
        ordered = sorted(
            high_signal,
            key=lambda event: (
                _event_datetime(event) or datetime.min.replace(tzinfo=UTC),
                event.id,
                event.type.value,
            ),
            reverse=True,
        )
        items = [
            RuntimeActivityItem(
                event_id=event.id,
                occurred_at=_event_datetime(event)
                or datetime.min.replace(tzinfo=UTC),
                event_type=event.type.value,
                severity=event.severity.value,
                summary=event.message,
                signal=_activity_signal(event),
            )
            for event in ordered[:DEFAULT_ACTIVITY_LIMIT]
        ]
        return RuntimeActivitySummary(
            generated_at=generated_at,
            recent_activity=items,
            high_signal_event_count=len(high_signal),
            metadata={
                "derived": True,
                "activity_limit": DEFAULT_ACTIVITY_LIMIT,
            },
        )

    def _safe_analytics(
        self,
        incomplete_reasons: list[str],
    ) -> RuntimeOperationalAnalytics:
        try:
            return self._analytics.generate()
        except Exception:
            incomplete_reasons.append("operational_analytics_unavailable")
            return _empty_analytics(self._clock())

    def _safe_health(
        self,
        incomplete_reasons: list[str],
    ) -> RuntimeHealthStatus:
        try:
            return self._health.evaluate()
        except Exception:
            incomplete_reasons.append("runtime_health_unavailable")
            return RuntimeHealthStatus(
                overall_status="unhealthy",
                generated_at=self._clock(),
                health_score=0,
                subsystem_results=[],
                findings=[],
                diagnostics={"check_available": False},
            )

    def _stale_projection_rebuild_count(
        self,
        generated_at: datetime,
    ) -> int:
        threshold = generated_at - timedelta(
            days=STALE_PROJECTION_REBUILD_DAYS,
        )
        count = 0
        for status in self._lifecycle.projection_statuses():
            completed_at = status.latest_rebuild_completed_at
            if completed_at is None or completed_at < threshold:
                count += 1
        return count

    def _source_events(self) -> list[RuntimeEvent]:
        return [
            event
            for event in self._events.list_persisted_events()
            if event.type.value not in INTELLIGENCE_EVENT_TYPES
        ]

    def _start_request(self) -> float:
        self._requests_total += 1
        return self._timer()

    def _record_success(
        self,
        started_at: float,
        view: str,
        risks: list[RuntimeRisk],
    ) -> None:
        duration_ms = self._duration_ms(started_at)
        self._risks_detected_total += len(risks)
        metrics = self.observability_metrics()
        self._events.emit_event_sync(
            event_type=EventType.RUNTIME_INTELLIGENCE_GENERATED,
            message="Runtime intelligence generated",
            metadata={
                "view": view,
                "intelligence_generation_duration_ms": duration_ms,
                **metrics,
            },
        )
        for risk in risks:
            self._events.emit_event_sync(
                event_type=EventType.RUNTIME_RISK_DETECTED,
                severity=(
                    Severity.CRITICAL
                    if risk.severity == "critical"
                    else Severity.WARNING
                ),
                message=risk.summary,
                metadata={
                    "risk_id": risk.risk_id,
                    "risk_severity": risk.severity,
                    "source": risk.source,
                    "evidence_count": risk.evidence_count,
                    **metrics,
                },
            )

    def _record_failure(self, started_at: float, exc: Exception) -> None:
        self._failures_total += 1
        self._events.emit_event_sync(
            event_type=EventType.RUNTIME_INTELLIGENCE_FAILED,
            severity=Severity.ERROR,
            message=f"Runtime intelligence failed: {exc}",
            metadata={
                "error_type": type(exc).__name__,
                "intelligence_generation_duration_ms": self._duration_ms(
                    started_at
                ),
                **self.observability_metrics(),
            },
        )

    def _duration_ms(self, started_at: float) -> float:
        return round(max(0.0, (self._timer() - started_at) * 1000), 3)


def _empty_analytics(generated_at: datetime) -> RuntimeOperationalAnalytics:
    return RuntimeOperationalAnalytics(
        generated_at=generated_at,
        total_sessions=0,
        active_sessions=0,
        completed_sessions=0,
        failed_sessions=0,
        total_events=0,
        total_proposals=0,
        total_decisions=0,
        total_artifacts=0,
        total_tool_executions=0,
        governance=GovernanceAnalytics(
            approvals=0,
            rejections=0,
            policy_evaluations=0,
            reflection_triggers=0,
            budget_actions=0,
            governance_activity_rate=0,
        ),
        projections=ProjectionAnalytics(
            registered_projections=0,
            projection_rebuilds=0,
            projection_replays=0,
            drift_checks=0,
            drift_detections=0,
            projection_failures=0,
        ),
        reconstruction=ReconstructionAnalytics(
            reconstructed_sessions=0,
            reconstruction_failures=0,
            incomplete_reconstructions=0,
            average_reconstruction_duration_ms=0,
        ),
        trends=RuntimeTrendAnalytics(
            lookback_days=DEFAULT_TREND_LOOKBACK_DAYS,
            buckets=[],
            events_per_day={},
            decisions_per_day={},
            artifacts_per_day={},
            governance_actions_per_day={},
        ),
        incomplete=True,
        incomplete_reasons=["operational_analytics_unavailable"],
        metadata={"derived": True},
    )


def _risk(
    risk_id: str,
    severity: RuntimeRiskSeverity,
    source: str,
    summary: str,
    evidence_count: int,
) -> RuntimeRisk:
    return RuntimeRisk(
        risk_id=risk_id,
        severity=severity,
        source=source,
        summary=summary,
        evidence_count=evidence_count,
    )


def _risk_level(risks: list[RuntimeRisk]) -> RuntimeRiskLevel:
    severities = {risk.severity for risk in risks}
    if "critical" in severities:
        return "critical"
    if "high" in severities:
        return "high"
    if "moderate" in severities:
        return "moderate"
    return "low"


def _risk_severity_rank(severity: str) -> int:
    return {"critical": 0, "high": 1, "moderate": 2}.get(severity, 3)


def _operator_attention_for(risk_id: str) -> str:
    return {
        "critical_runtime_health": "inspect_runtime_health",
        "projection_drift_detected": "review_projection_drift",
        "reconstruction_failures": "review_runtime_reconstruction_failures",
        "projection_replay_failures": "review_projection_replay_failures",
        "projection_rebuild_failures": "review_projection_rebuild_failures",
        "governance_rejection_spike": "review_governance_rejections",
        "incomplete_lineage_or_reconstruction": "review_lineage_completeness",
        "stale_projection_rebuilds": "rebuild_stale_projections",
    }[risk_id]


def _status_from_health(
    health: RuntimeHealthStatus,
) -> RuntimeIntelligenceStatus:
    return health.overall_status


def _status_for_projection_integrity(
    drift_detections: int,
    projection_failures: int,
    stale_rebuilds: int,
) -> RuntimeIntelligenceStatus:
    if drift_detections or projection_failures:
        return "degraded"
    if stale_rebuilds:
        return "warning"
    return "healthy"


def _status_for_reconstruction_integrity(
    reconstruction_failures: int,
    incomplete_count: int,
) -> RuntimeIntelligenceStatus:
    if reconstruction_failures:
        return "degraded"
    if incomplete_count:
        return "warning"
    return "healthy"


def _worst_status(
    statuses: list[RuntimeIntelligenceStatus],
) -> RuntimeIntelligenceStatus:
    rank = {
        "healthy": 0,
        "warning": 1,
        "degraded": 2,
        "unhealthy": 3,
    }
    return max(statuses, key=lambda status: rank[status])


def _event_count(events: list[RuntimeEvent], event_type: EventType) -> int:
    return sum(1 for event in events if event.type == event_type)


def _event_datetime(event: RuntimeEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(event.ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _activity_signal(event: RuntimeEvent) -> str:
    if event.type in {
        EventType.PROJECTION_DRIFT_DETECTED,
        EventType.PROJECTION_REBUILD_FAILED,
        EventType.PROJECTION_REPLAY_FAILED,
        EventType.PROJECTION_DRIFT_CHECK_FAILED,
    }:
        return "projection_integrity"
    if event.type in {
        EventType.RUNTIME_RECONSTRUCTION_VIEW_INCOMPLETE,
        EventType.RUNTIME_RECONSTRUCTION_VIEW_FAILED,
        EventType.DECISION_LINEAGE_INCOMPLETE,
        EventType.ARTIFACT_LINEAGE_INCOMPLETE,
    }:
        return "reconstruction_completeness"
    if "governance" in event.type.value:
        return "governance"
    return "runtime_diagnostic"


runtime_intelligence_service = RuntimeIntelligenceService()
