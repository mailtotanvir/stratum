from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from app.models.planner import PlannerRecommendationStatus
from app.models.proposal import ProposalStatus
from app.models.runtime_dashboard import (
    RuntimeDashboard,
    RuntimeDashboardSection,
)
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.models.runtime_session import RuntimeSessionStatus
from app.query.runtime_query_registry import (
    RuntimeQueryRegistry,
    runtime_query_registry,
)
from app.runtime.projection_registry import (
    ProjectionRegistry,
    projection_registry,
)
from app.services.decision_record_service import (
    DecisionRecordService,
    decision_record_service,
)
from app.services.diagnostics_service import (
    DiagnosticsService,
    diagnostics_service,
)
from app.services.event_service import EventService, event_service
from app.services.planner_recommendation_service import (
    PlannerRecommendationService,
    planner_recommendation_service,
)
from app.services.proposal_service import ProposalService, proposal_service
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)
from app.services.runtime_health_service import (
    RuntimeHealthService,
    runtime_health_service,
)


RUNTIME_VERSION = "0.6.0"
DASHBOARD_SECTION_VERSION = 1
DASHBOARD_SECTION_COUNT = 8
DASHBOARD_EVENT_TYPES = frozenset(
    {
        EventType.RUNTIME_DASHBOARD_GENERATED.value,
        EventType.RUNTIME_DASHBOARD_GENERATION_FAILED.value,
        EventType.RUNTIME_HEALTH_EVALUATED.value,
        EventType.RUNTIME_HEALTH_CHECK_FAILED.value,
    }
)


class RuntimeDashboardGenerationError(RuntimeError):
    pass


class RuntimeDashboardService:
    def __init__(
        self,
        events: EventService | None = None,
        sessions: RuntimeSessionService | None = None,
        decisions: DecisionRecordService | None = None,
        recommendations: PlannerRecommendationService | None = None,
        proposals: ProposalService | None = None,
        projections: ProjectionRegistry | None = None,
        queries: RuntimeQueryRegistry | None = None,
        diagnostics: DiagnosticsService | None = None,
        clock: Callable[[], datetime] | None = None,
        timer: Callable[[], float] | None = None,
        runtime_version: str = RUNTIME_VERSION,
        health: RuntimeHealthService | None = None,
    ) -> None:
        self._events = events or event_service
        self._sessions = sessions or runtime_session_service
        self._decisions = decisions or decision_record_service
        self._recommendations = (
            recommendations or planner_recommendation_service
        )
        self._proposals = proposals or proposal_service
        self._projections = projections or projection_registry
        self._queries = queries or runtime_query_registry
        self._diagnostics = diagnostics or diagnostics_service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._timer = timer or perf_counter
        self._runtime_version = runtime_version
        self._health = health or runtime_health_service

    def generate(self) -> RuntimeDashboard:
        started_at = self._timer()
        section_count = 0
        try:
            generated_at = self._clock()
            events = self._source_events()
            sessions = self._sessions.list_sessions()
            decisions = self._decisions.list_decision_records()
            recommendations = self._recommendations.list_recommendations()
            proposals = self._proposals.list_proposals()
            health = self._health.evaluate()
            sections = [
                self._runtime_section(generated_at, events, sessions),
                self._session_section(generated_at, sessions),
                self._decision_section(
                    generated_at,
                    decisions,
                    recommendations,
                ),
                self._projection_section(generated_at, events),
                self._query_section(generated_at, events),
                self._governance_section(
                    generated_at,
                    events,
                    proposals,
                ),
                self._diagnostics_section(generated_at, events),
                self._health_section(generated_at, health),
            ]
            section_count = len(sections)
            dashboard = RuntimeDashboard(
                generated_at=generated_at,
                runtime_summary=sections[0],
                session_summary=sections[1],
                decision_summary=sections[2],
                projection_summary=sections[3],
                query_summary=sections[4],
                governance_summary=sections[5],
                diagnostics_summary=sections[6],
                health_summary=sections[7],
            )
        except Exception as exc:
            duration_ms = self._duration_ms(started_at)
            self._events.emit_event_sync(
                event_type=EventType.RUNTIME_DASHBOARD_GENERATION_FAILED,
                severity=Severity.ERROR,
                message=f"Runtime dashboard generation failed: {exc}",
                metadata={
                    "generation_duration_ms": duration_ms,
                    "section_count": section_count,
                },
            )
            raise RuntimeDashboardGenerationError(
                f"Runtime dashboard generation failed: {exc}"
            ) from exc

        self._events.emit_event_sync(
            event_type=EventType.RUNTIME_DASHBOARD_GENERATED,
            message="Runtime dashboard generated",
            metadata={
                "generation_duration_ms": self._duration_ms(started_at),
                "section_count": section_count,
            },
        )
        return dashboard

    def _runtime_section(
        self,
        generated_at: datetime,
        events: list[RuntimeEvent],
        sessions: list[Any],
    ) -> RuntimeDashboardSection:
        session_counts = _session_counts(sessions)
        event_counts = Counter(event.type.value for event in events)
        return self._section(
            "runtime_summary",
            generated_at,
            {
                "runtime_version": self._runtime_version,
                "active_sessions": (
                    session_counts[RuntimeSessionStatus.CREATED.value]
                    + session_counts[RuntimeSessionStatus.RUNNING.value]
                ),
                "completed_sessions": session_counts[
                    RuntimeSessionStatus.COMPLETED.value
                ],
                "session_counts": session_counts,
                "event_counts": dict(sorted(event_counts.items())),
                "total_events": len(events),
            },
            sources=["runtime_session_service", "event_store"],
        )

    def _session_section(
        self,
        generated_at: datetime,
        sessions: list[Any],
    ) -> RuntimeDashboardSection:
        counts = _session_counts(sessions)
        return self._section(
            "session_summary",
            generated_at,
            {
                "total_sessions": len(sessions),
                "active_sessions": (
                    counts[RuntimeSessionStatus.CREATED.value]
                    + counts[RuntimeSessionStatus.RUNNING.value]
                ),
                "completed_sessions": counts[
                    RuntimeSessionStatus.COMPLETED.value
                ],
                "interrupted_sessions": counts[
                    RuntimeSessionStatus.INTERRUPTED.value
                ],
                "stopped_sessions": counts[
                    RuntimeSessionStatus.STOPPED.value
                ],
                "status_counts": counts,
            },
            sources=["runtime_session_service"],
        )

    def _decision_section(
        self,
        generated_at: datetime,
        decisions: list[Any],
        recommendations: list[Any],
    ) -> RuntimeDashboardSection:
        selected_count = sum(
            1
            for record in decisions
            if getattr(
                record,
                "selected_entity_type",
                "planner_recommendation",
            )
            == "planner_recommendation"
        )
        status_counts = {
            status.value: 0 for status in PlannerRecommendationStatus
        }
        for record in recommendations:
            status_counts[record.status] = (
                status_counts.get(record.status, 0) + 1
            )
        return self._section(
            "decision_summary",
            generated_at,
            {
                "decision_record_count": len(decisions),
                "recommendation_count": len(recommendations),
                "selected_recommendation_count": selected_count,
                "recommendation_status_counts": status_counts,
            },
            sources=[
                "decision_record_service",
                "planner_recommendation_service",
            ],
        )

    def _projection_section(
        self,
        generated_at: datetime,
        events: list[RuntimeEvent],
    ) -> RuntimeDashboardSection:
        registered = self._projections.list_projection_types()
        return self._section(
            "projection_summary",
            generated_at,
            {
                "registered_projections": registered,
                "registered_projection_count": len(registered),
                "projection_rebuild_count": _event_count(
                    events,
                    EventType.PROJECTION_REBUILD_COMPLETED,
                ),
                "projection_verification_count": _event_count(
                    events,
                    EventType.PROJECTION_VERIFICATION_COMPLETED,
                ),
            },
            sources=["projection_registry", "event_store"],
        )

    def _query_section(
        self,
        generated_at: datetime,
        events: list[RuntimeEvent],
    ) -> RuntimeDashboardSection:
        registered = self._queries.list_query_names()
        return self._section(
            "query_summary",
            generated_at,
            {
                "registered_queries": registered,
                "registered_query_count": len(registered),
                "query_execution_count": _event_count(
                    events,
                    EventType.RUNTIME_QUERY_EXECUTION_COMPLETED,
                ),
                "query_verification_count": _event_count(
                    events,
                    EventType.QUERY_VERIFICATION_COMPLETED,
                ),
            },
            sources=["runtime_query_registry", "event_store"],
        )

    def _governance_section(
        self,
        generated_at: datetime,
        events: list[RuntimeEvent],
        proposals: list[Any],
    ) -> RuntimeDashboardSection:
        status_counts = {
            status.value: 0 for status in ProposalStatus
        }
        for proposal in proposals:
            status_counts[proposal.status] = (
                status_counts.get(proposal.status, 0) + 1
            )
        governance = self._diagnostics.governance_health()
        governance_events = [
            event
            for event in events
            if "governance" in event.type.value
        ]
        return self._section(
            "governance_summary",
            generated_at,
            {
                "proposal_count": len(proposals),
                "approval_count": status_counts[
                    ProposalStatus.APPROVED.value
                ],
                "rejection_count": status_counts[
                    ProposalStatus.REJECTED.value
                ],
                "proposal_status_counts": status_counts,
                "governance_diagnostics": {
                    "status": governance["status"],
                    "highest_severity": governance["highest_severity"],
                    "has_critical": governance["has_critical"],
                    "error_budget_status": governance["error_budget"][
                        "status"
                    ],
                    "event_count": len(governance_events),
                },
            },
            sources=[
                "proposal_service",
                "diagnostics_service",
                "event_store",
            ],
        )

    def _diagnostics_section(
        self,
        generated_at: datetime,
        events: list[RuntimeEvent],
    ) -> RuntimeDashboardSection:
        severity_counts = Counter(
            event.severity.value for event in events
        )
        recent = [
            {
                "event_id": event.id,
                "timestamp": event.ts,
                "event_type": event.type.value,
                "severity": event.severity.value,
                "message": event.message,
            }
            for event in events[-10:]
        ]
        return self._section(
            "diagnostics_summary",
            generated_at,
            {
                "warning_count": severity_counts[
                    Severity.WARNING.value
                ],
                "error_count": (
                    severity_counts[Severity.ERROR.value]
                    + severity_counts[Severity.CRITICAL.value]
                ),
                "critical_count": severity_counts[
                    Severity.CRITICAL.value
                ],
                "recent_diagnostic_events": recent,
            },
            sources=["event_store"],
        )

    def _health_section(
        self,
        generated_at: datetime,
        health: Any,
    ) -> RuntimeDashboardSection:
        return self._section(
            "health_summary",
            generated_at,
            {
                "overall_status": health.overall_status,
                "health_score": health.health_score,
                "subsystems": [
                    {
                        "subsystem_name": result.subsystem_name,
                        "status": result.status,
                        "score": result.score,
                    }
                    for result in health.subsystem_results
                ],
            },
            sources=["runtime_health_service"],
        )

    @staticmethod
    def _section(
        section_name: str,
        generated_at: datetime,
        summary: dict[str, Any],
        *,
        sources: list[str],
    ) -> RuntimeDashboardSection:
        return RuntimeDashboardSection(
            section_name=section_name,
            section_version=DASHBOARD_SECTION_VERSION,
            generated_at=generated_at,
            summary=summary,
            metadata={
                "derived": True,
                "sources": sources,
            },
        )

    def _source_events(self) -> list[RuntimeEvent]:
        return [
            event
            for event in self._events.list_persisted_events()
            if event.type.value not in DASHBOARD_EVENT_TYPES
        ]

    def _duration_ms(self, started_at: float) -> float:
        return round(
            max(0.0, (self._timer() - started_at) * 1000),
            3,
        )


def _session_counts(sessions: list[Any]) -> dict[str, int]:
    counts = {status.value: 0 for status in RuntimeSessionStatus}
    for session in sessions:
        counts[session.status] = counts.get(session.status, 0) + 1
    return counts


def _event_count(
    events: list[RuntimeEvent],
    event_type: EventType,
) -> int:
    return sum(
        1 for event in events if event.type.value == event_type.value
    )


runtime_dashboard_service = RuntimeDashboardService()
