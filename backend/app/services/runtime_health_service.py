from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.models.runtime_health import (
    RuntimeHealthStatus,
    RuntimeSubsystemHealth,
)
from app.models.runtime_session import RuntimeSessionStatus
from app.services.diagnostics_service import (
    DiagnosticsService,
    diagnostics_service,
)
from app.services.event_service import EventService, event_service
from app.services.reconstruction_service import (
    ReconstructionService,
)
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)


HEALTH_SUBSYSTEMS = (
    "runtime",
    "governance",
    "planner",
    "projections",
    "queries",
    "diagnostics",
)
HEALTH_EVENT_TYPES = frozenset(
    {
        EventType.RUNTIME_HEALTH_EVALUATED.value,
        EventType.RUNTIME_HEALTH_CHECK_FAILED.value,
        EventType.RUNTIME_DASHBOARD_GENERATED.value,
        EventType.RUNTIME_DASHBOARD_GENERATION_FAILED.value,
    }
)


class RuntimeHealthService:
    def __init__(
        self,
        events: EventService | None = None,
        sessions: RuntimeSessionService | None = None,
        diagnostics: DiagnosticsService | None = None,
        reconstruction: ReconstructionService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._events = events or event_service
        self._sessions = sessions or runtime_session_service
        self._diagnostics = diagnostics or diagnostics_service
        self._reconstruction = reconstruction or ReconstructionService(
            events=self._events,
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    def evaluate(self) -> RuntimeHealthStatus:
        generated_at = self._clock()
        events = self._source_events()
        checks = {
            "runtime": lambda: self._runtime_health(events),
            "governance": lambda: self._governance_health(events),
            "planner": self._planner_health,
            "projections": lambda: self._projection_health(events),
            "queries": lambda: self._query_health(events),
            "diagnostics": lambda: self._diagnostics_health(events),
        }
        results = [
            self._evaluate_subsystem(name, checks[name])
            for name in HEALTH_SUBSYSTEMS
        ]
        score = round(
            sum(result.score for result in results) / len(results)
        )
        return RuntimeHealthStatus(
            overall_status=_status_for_score(score),
            generated_at=generated_at,
            health_score=score,
            subsystem_results=results,
            diagnostics=[
                {
                    "subsystem": result.subsystem_name,
                    "status": result.status,
                    "score": result.score,
                }
                for result in results
            ],
        )

    def _evaluate_subsystem(
        self,
        subsystem: str,
        check: Callable[[], RuntimeSubsystemHealth],
    ) -> RuntimeSubsystemHealth:
        try:
            result = check()
        except Exception as exc:
            result = RuntimeSubsystemHealth(
                subsystem_name=subsystem,
                status="unhealthy",
                score=0,
                findings=[
                    {
                        "finding_type": "health_check_failed",
                        "severity": "critical",
                        "message": str(exc),
                    }
                ],
                diagnostics={"check_error": str(exc)},
            )
            self._events.emit_event_sync(
                event_type=EventType.RUNTIME_HEALTH_CHECK_FAILED,
                severity=Severity.ERROR,
                message=f"Runtime health check failed: {subsystem}",
                metadata={
                    "subsystem": subsystem,
                    "status": result.status,
                    "score": result.score,
                },
            )
            return result

        self._events.emit_event_sync(
            event_type=EventType.RUNTIME_HEALTH_EVALUATED,
            message=f"Runtime health evaluated: {subsystem}",
            metadata={
                "subsystem": subsystem,
                "status": result.status,
                "score": result.score,
            },
        )
        return result

    def _runtime_health(
        self,
        events: list[RuntimeEvent],
    ) -> RuntimeSubsystemHealth:
        sessions = self._sessions.list_sessions()
        findings: list[dict[str, Any]] = []
        active_integrity_issues = 0
        for session in sessions:
            active = session.status in {
                RuntimeSessionStatus.CREATED.value,
                RuntimeSessionStatus.RUNNING.value,
            }
            terminal = session.status in {
                RuntimeSessionStatus.COMPLETED.value,
                RuntimeSessionStatus.INTERRUPTED.value,
                RuntimeSessionStatus.STOPPED.value,
            }
            if active and session.completed_at is not None:
                active_integrity_issues += 1
            if terminal and session.completed_at is None:
                active_integrity_issues += 1
        if active_integrity_issues:
            findings.append(
                _finding(
                    "session_integrity",
                    "error",
                    active_integrity_issues,
                    "Runtime session lifecycle fields are inconsistent",
                )
            )

        task_consistency = self._reconstruction.task_consistency_health()
        inconsistent_tasks = int(task_consistency["inconsistent"])
        if inconsistent_tasks:
            findings.append(
                _finding(
                    "reconstruction_inconsistency",
                    "error",
                    inconsistent_tasks,
                    "Task records do not match reconstructable event state",
                )
            )

        penalty = min(60, active_integrity_issues * 20)
        penalty += min(40, inconsistent_tasks * 20)
        return _subsystem(
            "runtime",
            penalty,
            findings,
            {
                "event_store_accessible": True,
                "event_count": len(events),
                "session_count": len(sessions),
                "active_session_integrity_issue_count": (
                    active_integrity_issues
                ),
                "reconstruction_inconsistency_count": inconsistent_tasks,
            },
        )

    def _projection_health(
        self,
        events: list[RuntimeEvent],
    ) -> RuntimeSubsystemHealth:
        rebuild_failures = _count(
            events,
            EventType.PROJECTION_REBUILD_FAILED,
        )
        verification_failures = _count(
            events,
            EventType.PROJECTION_VERIFICATION_FAILED,
        )
        contract_failures = sum(
            1
            for event in events
            if event.type
            in {
                EventType.PROJECTION_REBUILD_FAILED,
                EventType.PROJECTION_MANIFEST_GENERATION_FAILED,
            }
            and any(
                token in event.message.lower()
                for token in ("contract", "validation", "schema")
            )
        )
        findings = _failure_findings(
            [
                (
                    "projection_rebuild_failure",
                    rebuild_failures,
                    "Projection rebuilds failed",
                ),
                (
                    "projection_verification_failure",
                    verification_failures,
                    "Projection verification checks failed",
                ),
                (
                    "projection_contract_validation_failure",
                    contract_failures,
                    "Projection contract validation failed",
                ),
            ]
        )
        penalty = min(45, rebuild_failures * 15)
        penalty += min(45, verification_failures * 15)
        penalty += min(50, contract_failures * 25)
        return _subsystem(
            "projections",
            penalty,
            findings,
            {
                "rebuild_failure_count": rebuild_failures,
                "verification_failure_count": verification_failures,
                "contract_validation_failure_count": contract_failures,
            },
        )

    def _query_health(
        self,
        events: list[RuntimeEvent],
    ) -> RuntimeSubsystemHealth:
        verification_failures = _count(
            events,
            EventType.QUERY_VERIFICATION_FAILED,
        )
        execution_failures = _count(
            events,
            EventType.RUNTIME_QUERY_EXECUTION_FAILED,
        )
        reconstruction_failures = sum(
            1
            for event in events
            if (
                event.type
                in {
                    EventType.QUERY_VERIFICATION_FAILED,
                    EventType.QUERY_LINEAGE_GENERATION_FAILED,
                    EventType.QUERY_MANIFEST_GENERATION_FAILED,
                }
                and "reconstruction" in event.message.lower()
            )
        )
        findings = _failure_findings(
            [
                (
                    "query_verification_failure",
                    verification_failures,
                    "Query verification checks failed",
                ),
                (
                    "query_execution_failure",
                    execution_failures,
                    "Runtime query executions failed",
                ),
                (
                    "query_reconstruction_failure",
                    reconstruction_failures,
                    "Query reconstruction metadata was unusable",
                ),
            ]
        )
        penalty = min(45, verification_failures * 15)
        penalty += min(45, execution_failures * 15)
        penalty += min(50, reconstruction_failures * 25)
        return _subsystem(
            "queries",
            penalty,
            findings,
            {
                "verification_failure_count": verification_failures,
                "execution_failure_count": execution_failures,
                "reconstruction_failure_count": reconstruction_failures,
            },
        )

    def _governance_health(
        self,
        events: list[RuntimeEvent],
    ) -> RuntimeSubsystemHealth:
        proposal_consistency = (
            self._reconstruction.proposal_consistency_health()
        )
        inconsistent = int(proposal_consistency["inconsistent"])
        governance_events = [
            event
            for event in events
            if "governance" in event.type.value
        ]
        warning_count = sum(
            1
            for event in governance_events
            if event.severity == Severity.WARNING
        )
        error_count = sum(
            1
            for event in governance_events
            if event.severity in {Severity.ERROR, Severity.CRITICAL}
        )
        findings = _failure_findings(
            [
                (
                    "proposal_lifecycle_anomaly",
                    inconsistent,
                    "Proposal records do not match lifecycle events",
                ),
                (
                    "governance_warning",
                    warning_count,
                    "Governance warnings were emitted",
                ),
                (
                    "governance_error",
                    error_count,
                    "Governance errors were emitted",
                ),
            ]
        )
        penalty = min(50, inconsistent * 20)
        penalty += min(25, warning_count * 5)
        penalty += min(60, error_count * 20)
        return _subsystem(
            "governance",
            penalty,
            findings,
            {
                "proposal_lifecycle_anomaly_count": inconsistent,
                "approval_inconsistency_count": inconsistent,
                "governance_warning_count": warning_count,
                "governance_error_count": error_count,
            },
        )

    def _planner_health(self) -> RuntimeSubsystemHealth:
        health = self._diagnostics.planner_recommendation_health()
        consistency = health["consistency"]
        inconsistent = int(consistency["inconsistent"])
        findings = _failure_findings(
            [
                (
                    "planner_recommendation_inconsistency",
                    inconsistent,
                    "Planner recommendation lifecycle is inconsistent",
                ),
                (
                    "planner_snapshot_missing",
                    int(health["recommendations_missing_context_snapshot"]),
                    "Planner recommendations lack context snapshots",
                ),
            ]
        )
        missing_snapshots = int(
            health["recommendations_missing_context_snapshot"]
        )
        penalty = min(70, inconsistent * 25)
        penalty += min(30, missing_snapshots * 5)
        return _subsystem(
            "planner",
            penalty,
            findings,
            {
                "recommendation_inconsistency_count": inconsistent,
                "missing_context_snapshot_count": missing_snapshots,
            },
        )

    def _diagnostics_health(
        self,
        events: list[RuntimeEvent],
    ) -> RuntimeSubsystemHealth:
        counts = Counter(event.severity.value for event in events)
        warning_count = counts[Severity.WARNING.value]
        error_count = counts[Severity.ERROR.value]
        critical_count = counts[Severity.CRITICAL.value]
        findings = _failure_findings(
            [
                (
                    "diagnostic_warning",
                    warning_count,
                    "Warning diagnostics are present",
                ),
                (
                    "diagnostic_error",
                    error_count,
                    "Error diagnostics are present",
                ),
                (
                    "diagnostic_critical",
                    critical_count,
                    "Critical diagnostics are present",
                ),
            ]
        )
        penalty = min(30, warning_count * 3)
        penalty += min(60, error_count * 15)
        penalty += min(100, critical_count * 50)
        return _subsystem(
            "diagnostics",
            penalty,
            findings,
            {
                "warning_count": warning_count,
                "error_count": error_count,
                "critical_count": critical_count,
            },
        )

    def _source_events(self) -> list[RuntimeEvent]:
        return [
            event
            for event in self._events.list_persisted_events()
            if event.type.value not in HEALTH_EVENT_TYPES
        ]


def _subsystem(
    name: str,
    penalty: int,
    findings: list[dict[str, Any]],
    diagnostics: dict[str, Any],
) -> RuntimeSubsystemHealth:
    score = max(0, 100 - penalty)
    return RuntimeSubsystemHealth(
        subsystem_name=name,
        status=_status_for_score(score),
        score=score,
        findings=findings,
        diagnostics=diagnostics,
    )


def _status_for_score(score: int) -> str:
    if score >= 90:
        return "healthy"
    if score >= 75:
        return "warning"
    if score >= 50:
        return "degraded"
    return "unhealthy"


def _count(
    events: list[RuntimeEvent],
    event_type: EventType,
) -> int:
    return sum(1 for event in events if event.type == event_type)


def _finding(
    finding_type: str,
    severity: str,
    count: int,
    message: str,
) -> dict[str, Any]:
    return {
        "finding_type": finding_type,
        "severity": severity,
        "count": count,
        "message": message,
    }


def _failure_findings(
    definitions: list[tuple[str, int, str]],
) -> list[dict[str, Any]]:
    return [
        _finding(finding_type, "error", count, message)
        for finding_type, count, message in definitions
        if count > 0
    ]


runtime_health_service = RuntimeHealthService()
