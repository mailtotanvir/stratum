from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.models.runtime_health import (
    RuntimeHealthFinding,
    RuntimeHealthStatus,
    RuntimeHealthStatusValue,
    RuntimeSubsystemHealth,
)
from app.models.runtime_session import RuntimeSessionStatus
from app.services.diagnostics_service import (
    DiagnosticsService,
    diagnostics_service,
)
from app.services.event_service import EventService, event_service
from app.services.reconstruction_service import ReconstructionService
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

# Health and dashboard reads must not degrade later health evaluations.
HEALTH_EVENT_TYPES = frozenset(
    {
        EventType.RUNTIME_HEALTH_EVALUATED.value,
        EventType.RUNTIME_HEALTH_SUBSYSTEM_EVALUATED.value,
        EventType.RUNTIME_HEALTH_CHECK_FAILED.value,
        EventType.RUNTIME_DASHBOARD_GENERATED.value,
        EventType.RUNTIME_DASHBOARD_GENERATION_FAILED.value,
    }
)


@dataclass(frozen=True)
class ScoreRule:
    penalty_per_occurrence: int
    maximum_penalty: int


STATUS_THRESHOLDS: tuple[
    tuple[int, RuntimeHealthStatusValue], ...
] = (
    (90, "healthy"),
    (75, "warning"),
    (50, "degraded"),
    (0, "unhealthy"),
)

# All scoring values are centralized here. Each check is independently
# bounded so one noisy signal cannot produce an unbounded penalty.
HEALTH_SCORING_POLICY: dict[str, ScoreRule] = {
    "runtime.session_integrity": ScoreRule(20, 60),
    "runtime.reconstruction_inconsistency": ScoreRule(20, 40),
    "governance.proposal_lifecycle_anomaly": ScoreRule(20, 50),
    "governance.governance_warning": ScoreRule(5, 25),
    "governance.governance_error": ScoreRule(20, 60),
    "planner.reconstruction_failure": ScoreRule(25, 70),
    "planner.input_diagnostic": ScoreRule(5, 30),
    "projections.rebuild_failure": ScoreRule(15, 45),
    "projections.verification_failure": ScoreRule(15, 45),
    "projections.contract_validation_failure": ScoreRule(25, 50),
    "queries.verification_failure": ScoreRule(15, 45),
    "queries.execution_failure": ScoreRule(15, 45),
    "queries.reconstruction_failure": ScoreRule(25, 50),
    "diagnostics.warning": ScoreRule(3, 30),
    "diagnostics.error": ScoreRule(15, 60),
    "diagnostics.critical": ScoreRule(50, 100),
}


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
            "planner": lambda: self._planner_health(events),
            "projections": lambda: self._projection_health(events),
            "queries": lambda: self._query_health(events),
            "diagnostics": lambda: self._diagnostics_health(events),
        }
        results = [
            self._evaluate_subsystem(name, checks[name])
            for name in HEALTH_SUBSYSTEMS
        ]
        findings = [
            finding
            for result in results
            for finding in result.findings
        ]
        score = round(
            sum(result.score for result in results) / len(results)
        )
        status = _status_for_score(score)
        result = RuntimeHealthStatus(
            overall_status=status,
            generated_at=generated_at,
            health_score=score,
            subsystem_results=results,
            findings=findings,
            diagnostics={
                "subsystem_count": len(results),
                "finding_count": len(findings),
                "scoring_policy": "bounded_penalty_mean_v1",
                "subsystems": [
                    {
                        "subsystem": item.subsystem_name,
                        "status": item.status,
                        "score": item.score,
                        "finding_count": len(item.findings),
                    }
                    for item in results
                ],
            },
        )
        self._emit_health_event(
            EventType.RUNTIME_HEALTH_EVALUATED,
            subsystem="overall",
            status=status,
            score=score,
            finding_count=len(findings),
        )
        return result

    def _evaluate_subsystem(
        self,
        subsystem: str,
        check: Callable[[], RuntimeSubsystemHealth],
    ) -> RuntimeSubsystemHealth:
        try:
            result = check()
        except Exception as exc:
            finding = _finding(
                subsystem,
                "health_check_failed",
                "critical",
                f"Runtime health check failed: {exc}",
                error_type=type(exc).__name__,
            )
            result = RuntimeSubsystemHealth(
                subsystem_name=subsystem,
                status="unhealthy",
                score=0,
                findings=[finding],
                diagnostics={
                    "check_available": False,
                    "check_error": str(exc),
                },
            )
            self._emit_health_event(
                EventType.RUNTIME_HEALTH_CHECK_FAILED,
                subsystem=subsystem,
                status=result.status,
                score=result.score,
                finding_count=1,
                severity=Severity.ERROR,
            )
            return result

        self._emit_health_event(
            EventType.RUNTIME_HEALTH_SUBSYSTEM_EVALUATED,
            subsystem=subsystem,
            status=result.status,
            score=result.score,
            finding_count=len(result.findings),
        )
        return result

    def _runtime_health(
        self,
        events: list[RuntimeEvent],
    ) -> RuntimeSubsystemHealth:
        sessions = self._sessions.list_sessions()
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

        task_consistency = self._reconstruction.task_consistency_health()
        inconsistent_tasks = int(task_consistency["inconsistent"])
        findings = _findings(
            "runtime",
            [
                (
                    "session_integrity",
                    "error",
                    active_integrity_issues,
                    "Runtime session lifecycle fields are inconsistent",
                ),
                (
                    "reconstruction_inconsistency",
                    "error",
                    inconsistent_tasks,
                    "Task records do not match reconstructable event state",
                ),
            ],
        )
        return _subsystem(
            "runtime",
            _penalty(
                "runtime.session_integrity",
                active_integrity_issues,
            )
            + _penalty(
                "runtime.reconstruction_inconsistency",
                inconsistent_tasks,
            ),
            findings,
            {
                "event_store_accessible": True,
                "reconstruction_available": True,
                "runtime_service_available": True,
                "event_count": len(events),
                "session_count": len(sessions),
                "active_session_integrity_issue_count": (
                    active_integrity_issues
                ),
                "reconstruction_inconsistency_count": inconsistent_tasks,
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
            event.severity == Severity.WARNING
            for event in governance_events
        )
        error_count = sum(
            event.severity in {Severity.ERROR, Severity.CRITICAL}
            for event in governance_events
        )
        findings = _findings(
            "governance",
            [
                (
                    "proposal_lifecycle_anomaly",
                    "error",
                    inconsistent,
                    "Proposal records do not match lifecycle events",
                ),
                (
                    "governance_warning",
                    "warning",
                    warning_count,
                    "Governance warnings were emitted",
                ),
                (
                    "governance_error",
                    "error",
                    error_count,
                    "Governance errors were emitted",
                ),
            ],
        )
        return _subsystem(
            "governance",
            _penalty(
                "governance.proposal_lifecycle_anomaly",
                inconsistent,
            )
            + _penalty(
                "governance.governance_warning",
                warning_count,
            )
            + _penalty(
                "governance.governance_error",
                error_count,
            ),
            findings,
            {
                "proposal_lifecycle_anomaly_count": inconsistent,
                "approval_inconsistency_count": inconsistent,
                "governance_warning_count": warning_count,
                "governance_error_count": error_count,
            },
        )

    def _planner_health(
        self,
        events: list[RuntimeEvent],
    ) -> RuntimeSubsystemHealth:
        health = self._diagnostics.planner_recommendation_health()
        reconstruction_failures = int(
            health["consistency"]["inconsistent"]
        )
        missing_snapshots = int(
            health["recommendations_missing_context_snapshot"]
        )
        input_diagnostics = sum(
            event.type == EventType.PLANNER_INPUT_BUILT
            and event.severity
            in {Severity.WARNING, Severity.ERROR, Severity.CRITICAL}
            for event in events
        )
        input_issue_count = missing_snapshots + input_diagnostics
        findings = _findings(
            "planner",
            [
                (
                    "planner_reconstruction_failure",
                    "error",
                    reconstruction_failures,
                    "Planner recommendation reconstruction is inconsistent",
                ),
                (
                    "planner_input_build_diagnostic",
                    "warning",
                    input_issue_count,
                    "Planner input build diagnostics require attention",
                ),
            ],
        )
        return _subsystem(
            "planner",
            _penalty(
                "planner.reconstruction_failure",
                reconstruction_failures,
            )
            + _penalty(
                "planner.input_diagnostic",
                input_issue_count,
            ),
            findings,
            {
                "planner_reconstruction_failure_count": (
                    reconstruction_failures
                ),
                "planner_input_build_diagnostic_count": input_diagnostics,
                "missing_context_snapshot_count": missing_snapshots,
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
            event.type
            in {
                EventType.PROJECTION_REBUILD_FAILED,
                EventType.PROJECTION_MANIFEST_GENERATION_FAILED,
            }
            and any(
                token in event.message.lower()
                for token in ("contract", "validation", "schema")
            )
            for event in events
        )
        findings = _findings(
            "projections",
            [
                (
                    "projection_rebuild_failure",
                    "error",
                    rebuild_failures,
                    "Projection rebuilds failed",
                ),
                (
                    "projection_verification_failure",
                    "error",
                    verification_failures,
                    "Projection verification checks failed",
                ),
                (
                    "projection_contract_validation_failure",
                    "error",
                    contract_failures,
                    "Projection contract validation failed",
                ),
            ],
        )
        return _subsystem(
            "projections",
            _penalty(
                "projections.rebuild_failure",
                rebuild_failures,
            )
            + _penalty(
                "projections.verification_failure",
                verification_failures,
            )
            + _penalty(
                "projections.contract_validation_failure",
                contract_failures,
            ),
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
            event.type
            in {
                EventType.QUERY_VERIFICATION_FAILED,
                EventType.QUERY_LINEAGE_GENERATION_FAILED,
                EventType.QUERY_MANIFEST_GENERATION_FAILED,
            }
            and "reconstruction" in event.message.lower()
            for event in events
        )
        findings = _findings(
            "queries",
            [
                (
                    "query_verification_failure",
                    "error",
                    verification_failures,
                    "Query verification checks failed",
                ),
                (
                    "query_execution_failure",
                    "error",
                    execution_failures,
                    "Runtime query executions failed",
                ),
                (
                    "query_reconstruction_failure",
                    "error",
                    reconstruction_failures,
                    "Query reconstruction metadata was unusable",
                ),
            ],
        )
        return _subsystem(
            "queries",
            _penalty(
                "queries.verification_failure",
                verification_failures,
            )
            + _penalty(
                "queries.execution_failure",
                execution_failures,
            )
            + _penalty(
                "queries.reconstruction_failure",
                reconstruction_failures,
            ),
            findings,
            {
                "verification_failure_count": verification_failures,
                "execution_failure_count": execution_failures,
                "reconstruction_failure_count": reconstruction_failures,
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
        findings = _findings(
            "diagnostics",
            [
                (
                    "diagnostic_warning",
                    "warning",
                    warning_count,
                    "Warning diagnostics are present",
                ),
                (
                    "diagnostic_error",
                    "error",
                    error_count,
                    "Error diagnostics are present",
                ),
                (
                    "diagnostic_critical",
                    "critical",
                    critical_count,
                    "Critical diagnostics are present",
                ),
            ],
        )
        return _subsystem(
            "diagnostics",
            _penalty("diagnostics.warning", warning_count)
            + _penalty("diagnostics.error", error_count)
            + _penalty("diagnostics.critical", critical_count),
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

    def _emit_health_event(
        self,
        event_type: EventType,
        *,
        subsystem: str,
        status: RuntimeHealthStatusValue,
        score: int,
        finding_count: int,
        severity: Severity = Severity.INFO,
    ) -> None:
        self._events.emit_event_sync(
            event_type=event_type,
            severity=severity,
            message=f"Runtime health evaluated: {subsystem}",
            metadata={
                "subsystem": subsystem,
                "status": status,
                "score": score,
                "finding_count": finding_count,
            },
        )


def _subsystem(
    name: str,
    penalty: int,
    findings: list[RuntimeHealthFinding],
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


def _status_for_score(score: int) -> RuntimeHealthStatusValue:
    for minimum, status in STATUS_THRESHOLDS:
        if score >= minimum:
            return status
    raise ValueError(f"Health score is outside the supported range: {score}")


def _penalty(policy_name: str, count: int) -> int:
    rule = HEALTH_SCORING_POLICY[policy_name]
    return min(
        rule.maximum_penalty,
        count * rule.penalty_per_occurrence,
    )


def _count(
    events: list[RuntimeEvent],
    event_type: EventType,
) -> int:
    return sum(event.type == event_type for event in events)


def _finding(
    subsystem: str,
    finding_type: str,
    severity: str,
    summary: str,
    **metadata: Any,
) -> RuntimeHealthFinding:
    return RuntimeHealthFinding(
        finding_id=f"{subsystem}:{finding_type}",
        finding_type=finding_type,
        severity=severity,
        subsystem=subsystem,
        summary=summary,
        metadata=metadata,
    )


def _findings(
    subsystem: str,
    definitions: list[tuple[str, str, int, str]],
) -> list[RuntimeHealthFinding]:
    return [
        _finding(
            subsystem,
            finding_type,
            severity,
            summary,
            count=count,
        )
        for finding_type, severity, count, summary in definitions
        if count > 0
    ]


runtime_health_service = RuntimeHealthService()
