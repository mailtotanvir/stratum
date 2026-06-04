from typing import Any

from app.models.proposal import ProposalStatus
from app.models.runtime_event import EventType, Severity
from app.models.task import TaskStatus
from app.services.event_service import EventService, event_service
from app.services.governance_service import (
    GovernanceService,
    classify_governance_status,
)
from app.services.proposal_service import ProposalService, proposal_service
from app.services.reconstruction_service import ReconstructionService
from app.services.task_service import TaskService, task_service


TASK_LIFECYCLE_TYPES = [
    EventType.TASK_CREATED.value,
    EventType.TASK_RUNNING.value,
    EventType.TASK_COMPLETED.value,
    EventType.TASK_FAILED.value,
]

PROPOSAL_LIFECYCLE_TYPES = [
    EventType.PROPOSAL_GENERATED.value,
    EventType.PROPOSAL_RESOLVED.value,
]

SEVERITY_RANK = {
    Severity.INFO.value: 0,
    Severity.WARNING.value: 1,
    Severity.ERROR.value: 2,
    Severity.CRITICAL.value: 3,
}


class DiagnosticsService:
    def __init__(
        self,
        events: EventService | None = None,
        tasks: TaskService | None = None,
        proposals: ProposalService | None = None,
        reconstruction: ReconstructionService | None = None,
        governance: GovernanceService | None = None,
    ) -> None:
        self._events = events or event_service
        self._tasks = tasks or task_service
        self._proposals = proposals or proposal_service
        self._governance = governance or GovernanceService(self._events)
        self._reconstruction = reconstruction or ReconstructionService(
            events=self._events,
            tasks=self._tasks,
            proposals=self._proposals,
        )

    def event_store_health(self) -> dict[str, Any]:
        events = self._events.list_persisted_events()
        event_type_counts: dict[str, int] = {}
        lifecycle_event_counts = {
            event_type: 0 for event_type in TASK_LIFECYCLE_TYPES
        }
        missing_task_id_count = 0
        missing_task_id_by_type: dict[str, int] = {}
        missing_proposal_id_by_type: dict[str, int] = {}

        for event in events:
            event_type = event.type.value
            event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1

            if event_type in lifecycle_event_counts:
                lifecycle_event_counts[event_type] += 1
                if not isinstance(event.metadata.get("task_id"), str):
                    missing_task_id_count += 1
                    missing_task_id_by_type[event_type] = (
                        missing_task_id_by_type.get(event_type, 0) + 1
                    )
            if event_type in PROPOSAL_LIFECYCLE_TYPES and not isinstance(
                event.metadata.get("proposal_id"), str
            ):
                missing_proposal_id_by_type[event_type] = (
                    missing_proposal_id_by_type.get(event_type, 0) + 1
                )

        latest_event = events[-1] if events else None

        return {
            "total_events": len(events),
            "event_type_counts": event_type_counts,
            "lifecycle_event_counts": lifecycle_event_counts,
            "missing_task_id_count": missing_task_id_count,
            "missing_task_id_by_type": missing_task_id_by_type,
            "missing_proposal_id_by_type": missing_proposal_id_by_type,
            "latest_event_timestamp": latest_event.ts if latest_event else None,
            "latest_event_type": latest_event.type.value if latest_event else None,
        }

    def proposal_health(self) -> dict[str, Any]:
        proposals = self._proposals.list_proposals()
        status_counts = {
            ProposalStatus.PROPOSED.value: 0,
            ProposalStatus.APPROVED.value: 0,
            ProposalStatus.REJECTED.value: 0,
        }
        for proposal in proposals:
            if proposal.status in status_counts:
                status_counts[proposal.status] += 1

        proposal_events = [
            event
            for event in self._events.list_persisted_events()
            if event.type.value in PROPOSAL_LIFECYCLE_TYPES
        ]
        event_counts = {
            event_type: 0 for event_type in PROPOSAL_LIFECYCLE_TYPES
        }
        missing_proposal_id_count = 0
        missing_proposal_id_by_type: dict[str, int] = {}

        for event in proposal_events:
            event_counts[event.type.value] += 1
            if not isinstance(event.metadata.get("proposal_id"), str):
                missing_proposal_id_count += 1
                missing_proposal_id_by_type[event.type.value] = (
                    missing_proposal_id_by_type.get(event.type.value, 0) + 1
                )

        latest_event = proposal_events[-1] if proposal_events else None

        return {
            "total_proposals": len(proposals),
            "status_counts": status_counts,
            "event_counts": event_counts,
            "unresolved_count": status_counts[ProposalStatus.PROPOSED.value],
            "missing_proposal_id_count": missing_proposal_id_count,
            "missing_proposal_id_by_type": missing_proposal_id_by_type,
            "latest_proposal_event_timestamp": (
                latest_event.ts if latest_event else None
            ),
            "latest_proposal_event_type": (
                latest_event.type.value if latest_event else None
            ),
        }

    def governance_health(self) -> dict[str, Any]:
        events = self._events.list_persisted_events()
        error_budget = self._governance.evaluate_error_budget()
        severity_counts = {severity.value: 0 for severity in Severity}
        highest_severity: str | None = None

        for event in events:
            severity = event.severity.value
            severity_counts[severity] += 1
            if highest_severity is None or (
                SEVERITY_RANK[severity] > SEVERITY_RANK[highest_severity]
            ):
                highest_severity = severity

        return {
            "severity_counts": severity_counts,
            "highest_severity": highest_severity,
            "has_critical": severity_counts[Severity.CRITICAL.value] > 0,
            "status": classify_governance_status(severity_counts),
            "error_budget": {
                "status": error_budget["status"],
                "exhausted": error_budget["exhausted"],
            },
            "total_governance_events": len(events),
        }

    def runtime_summary(self) -> dict[str, Any]:
        event_health = self.event_store_health()
        task_health = self._task_health()
        proposal_health = self.proposal_health()
        governance_health = self.governance_health()
        task_consistency = self._reconstruction.task_consistency_health()
        proposal_consistency = self._reconstruction.proposal_consistency_health()

        return {
            "events": {
                "total_events": event_health["total_events"],
                "latest_event_timestamp": event_health["latest_event_timestamp"],
                "latest_event_type": event_health["latest_event_type"],
            },
            "tasks": {
                "total_tasks": task_health["total_tasks"],
                "status_counts": task_health["status_counts"],
                "inconsistent": task_consistency["inconsistent"],
            },
            "proposals": {
                "total_proposals": proposal_health["total_proposals"],
                "status_counts": proposal_health["status_counts"],
                "unresolved_count": proposal_health["unresolved_count"],
                "inconsistent": proposal_consistency["inconsistent"],
            },
            "integrity": {
                "missing_task_id_count": event_health["missing_task_id_count"],
                "missing_proposal_id_count": proposal_health[
                    "missing_proposal_id_count"
                ],
            },
            "governance": {
                "severity_counts": governance_health["severity_counts"],
                "highest_severity": governance_health["highest_severity"],
                "has_critical": governance_health["has_critical"],
                "status": governance_health["status"],
                "error_budget": {
                    "status": governance_health["error_budget"]["status"],
                },
            },
        }

    def _task_health(self) -> dict[str, Any]:
        tasks = self._tasks.list_tasks()
        status_counts = {
            TaskStatus.CREATED.value: 0,
            TaskStatus.RUNNING.value: 0,
            TaskStatus.COMPLETED.value: 0,
            TaskStatus.FAILED.value: 0,
        }
        for task in tasks:
            if task.status in status_counts:
                status_counts[task.status] += 1

        return {
            "total_tasks": len(tasks),
            "status_counts": status_counts,
        }


diagnostics_service = DiagnosticsService()
