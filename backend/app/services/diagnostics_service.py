from typing import Any

from app.models.proposal import ProposalSourceType, ProposalStatus
from app.models.planning_context_snapshot import (
    LEGACY_OR_UNKNOWN_SNAPSHOT_VERSION,
    validate_planning_context_snapshot,
)
from app.models.planner import PlannerRecommendationStatus
from app.models.runtime_event import EventType, Severity
from app.models.task import TaskStatus
from app.services.decision_evidence_service import (
    DecisionEvidenceService,
    decision_evidence_service,
)
from app.services.decision_trail_service import DecisionTrailService
from app.services.event_service import EventService, event_service
from app.services.evaluation_diagnostics_service import (
    EvaluationDiagnosticsService,
    evaluation_diagnostics_service,
)
from app.services.decision_record_service import (
    DecisionRecordService,
    decision_record_service,
)
from app.services.governance_service import (
    GovernanceService,
    classify_governance_status,
)
from app.services.planner_recommendation_service import (
    PlannerRecommendationService,
    planner_recommendation_service,
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
        recommendations: PlannerRecommendationService | None = None,
        decisions: DecisionRecordService | None = None,
        decision_evidence: DecisionEvidenceService | None = None,
        decision_trails: DecisionTrailService | None = None,
        reconstruction: ReconstructionService | None = None,
        governance: GovernanceService | None = None,
        evaluation_diagnostics: EvaluationDiagnosticsService | None = None,
    ) -> None:
        self._events = events or event_service
        self._tasks = tasks or task_service
        self._proposals = proposals or proposal_service
        self._recommendations = recommendations or planner_recommendation_service
        self._decisions = decisions or decision_record_service
        self._decision_evidence = decision_evidence or decision_evidence_service
        self._governance = governance or GovernanceService(self._events)
        self._evaluation_diagnostics = (
            evaluation_diagnostics or evaluation_diagnostics_service
        )
        self._reconstruction = reconstruction or ReconstructionService(
            events=self._events,
            tasks=self._tasks,
            proposals=self._proposals,
            recommendations=self._recommendations,
        )
        self._decision_trails = decision_trails or DecisionTrailService(
            self._reconstruction
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
        source_type_counts = {
            source_type.value: 0 for source_type in ProposalSourceType
        }
        sources: list[dict[str, str | None]] = []
        planner_source_snapshot_count = 0
        planner_source_missing_snapshot_count = 0
        source_snapshot_version_counts: dict[str, int] = {}
        planner_source_legacy_or_unknown_count = 0
        for proposal in proposals:
            if proposal.status in status_counts:
                status_counts[proposal.status] += 1
            source_type = proposal.source_type or ProposalSourceType.MANUAL.value
            source_type_counts[source_type] = (
                source_type_counts.get(source_type, 0) + 1
            )
            source = {
                "proposal_id": proposal.id,
                "source_type": source_type,
                "source_id": proposal.source_id,
            }
            if source_type == ProposalSourceType.PLANNER_RECOMMENDATION.value:
                source["recommendation_id"] = proposal.source_id
                source_snapshot = self._proposals.source_context_snapshot_for(
                    proposal
                )
                if source_snapshot is None:
                    planner_source_missing_snapshot_count += 1
                else:
                    planner_source_snapshot_count += 1
                    validation = validate_planning_context_snapshot(
                        source_snapshot
                    )
                    classification = validation["classification"]
                    source_snapshot_version_counts[classification] = (
                        source_snapshot_version_counts.get(classification, 0)
                        + 1
                    )
                    if (
                        classification
                        == LEGACY_OR_UNKNOWN_SNAPSHOT_VERSION
                    ):
                        planner_source_legacy_or_unknown_count += 1
            sources.append(source)

        proposal_events = [
            event
            for event in self._events.list_persisted_events()
            if event.type.value in PROPOSAL_LIFECYCLE_TYPES
        ]
        event_counts = {
            event_type: 0 for event_type in PROPOSAL_LIFECYCLE_TYPES
        }
        event_source_type_counts = {
            source_type.value: 0 for source_type in ProposalSourceType
        }
        missing_proposal_id_count = 0
        missing_proposal_id_by_type: dict[str, int] = {}

        for event in proposal_events:
            event_counts[event.type.value] += 1
            event_source_type = event.metadata.get(
                "source_type",
                ProposalSourceType.MANUAL.value,
            )
            if isinstance(event_source_type, str):
                event_source_type_counts[event_source_type] = (
                    event_source_type_counts.get(event_source_type, 0) + 1
                )
            if not isinstance(event.metadata.get("proposal_id"), str):
                missing_proposal_id_count += 1
                missing_proposal_id_by_type[event.type.value] = (
                    missing_proposal_id_by_type.get(event.type.value, 0) + 1
                )

        latest_event = proposal_events[-1] if proposal_events else None

        return {
            "total_proposals": len(proposals),
            "status_counts": status_counts,
            "source_type_counts": source_type_counts,
            "proposals_with_source_context_snapshot": (
                planner_source_snapshot_count
            ),
            "proposals_missing_source_context_snapshot": (
                planner_source_missing_snapshot_count
            ),
            "proposal_source_context_snapshot_version_counts": (
                source_snapshot_version_counts
            ),
            "proposals_with_legacy_or_unknown_source_context_snapshot": (
                planner_source_legacy_or_unknown_count
            ),
            "sources": sources,
            "event_counts": event_counts,
            "event_source_type_counts": event_source_type_counts,
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

    def planner_recommendation_health(self) -> dict[str, Any]:
        records = self._recommendations.list_recommendations()
        reconstructed = self._reconstruction.get_reconstructed_recommendations()
        reconstructed_by_id = {
            recommendation["recommendation_id"]: recommendation
            for recommendation in reconstructed
        }
        governance_status_counts: dict[str, int] = {}
        status_counts = {
            status.value: 0 for status in PlannerRecommendationStatus
        }
        by_session_id: dict[str, list[str]] = {}

        for record in records:
            governance_status_counts[record.governance_status] = (
                governance_status_counts.get(record.governance_status, 0) + 1
            )
            status_counts[record.status] = status_counts.get(record.status, 0) + 1
            by_session_id.setdefault(record.session_id, []).append(record.id)

        promoted_count = sum(
            1
            for record in records
            if reconstructed_by_id.get(record.id, {}).get("promoted") is True
        )
        unpromoted_count = len(records) - promoted_count
        context_snapshot_count = sum(
            1
            for record in records
            if self._recommendations.context_snapshot_for(record) is not None
        )
        context_snapshot_version_counts: dict[str, int] = {}
        legacy_or_unknown_context_snapshot_count = 0
        for record in records:
            context_snapshot = self._recommendations.context_snapshot_for(record)
            if context_snapshot is None:
                continue
            validation = validate_planning_context_snapshot(context_snapshot)
            classification = validation["classification"]
            context_snapshot_version_counts[classification] = (
                context_snapshot_version_counts.get(classification, 0) + 1
            )
            if classification == LEGACY_OR_UNKNOWN_SNAPSHOT_VERSION:
                legacy_or_unknown_context_snapshot_count += 1
        consistency = self._reconstruction.recommendation_consistency_health()

        return {
            "total_recommendations": len(records),
            "recommendation_context_snapshot_count": context_snapshot_count,
            "recommendations_missing_context_snapshot": (
                len(records) - context_snapshot_count
            ),
            "recommendation_context_snapshot_version_counts": (
                context_snapshot_version_counts
            ),
            "recommendations_with_legacy_or_unknown_context_snapshot": (
                legacy_or_unknown_context_snapshot_count
            ),
            "governance_status_counts": governance_status_counts,
            "planner_recommendation_status_counts": status_counts,
            "promoted_count": promoted_count,
            "unpromoted_count": unpromoted_count,
            "by_session_id": by_session_id,
            "invalid_recommendation_status_transition_count": consistency[
                "invalid_recommendation_status_transition_count"
            ],
            "missing_recommendation_lifecycle_reference_count": consistency[
                "missing_recommendation_lifecycle_reference_count"
            ],
            "duplicate_recommendation_terminal_event_count": consistency[
                "duplicate_recommendation_terminal_event_count"
            ],
            "recommendation_lifecycle_issues": consistency["lifecycle_issues"],
            "consistency": consistency,
        }

    def decision_record_health(self) -> dict[str, Any]:
        records = self._decisions.list_decision_records()
        counts_by_type: dict[str, int] = {}
        for record in records:
            counts_by_type[record.decision_type] = (
                counts_by_type.get(record.decision_type, 0) + 1
            )
        return {
            "decision_record_count": len(records),
            "decision_record_counts_by_type": counts_by_type,
        }

    def decision_evidence_health(self) -> dict[str, Any]:
        records = self._decision_evidence.list_evidence()
        counts_by_type: dict[str, int] = {}
        for record in records:
            counts_by_type[record.evidence_type] = (
                counts_by_type.get(record.evidence_type, 0) + 1
            )
        return {
            "decision_evidence_count": len(records),
            "decision_evidence_counts_by_type": counts_by_type,
        }

    def decision_trail_health(self) -> dict[str, Any]:
        issues: list[dict[str, str | None]] = []
        complete_count = 0
        proposals = self._proposals.list_proposals()
        for proposal in proposals:
            trail = self._decision_trails.reconstruct(proposal.id)
            recommendation_id = trail.recommendation_id
            recommendation_found = (
                recommendation_id is not None
                and self._reconstruction.get_recommendation_lineage(
                    recommendation_id
                ).get("found")
            )
            if not recommendation_found:
                issues.append(
                    {
                        "issue_type": "proposal_missing_recommendation_source",
                        "proposal_id": proposal.id,
                        "recommendation_id": recommendation_id,
                        "decision_id": None,
                    }
                )
                continue
            if trail.decision_id is None:
                issues.append(
                    {
                        "issue_type": "recommendation_missing_decision_record",
                        "proposal_id": proposal.id,
                        "recommendation_id": recommendation_id,
                        "decision_id": None,
                    }
                )
                continue
            if not trail.evidence_ids:
                issues.append(
                    {
                        "issue_type": "decision_record_missing_evidence",
                        "proposal_id": proposal.id,
                        "recommendation_id": recommendation_id,
                        "decision_id": trail.decision_id,
                    }
                )
                continue
            complete_count += 1

        total = len(proposals)
        return {
            "proposals_with_decision_trails": complete_count,
            "proposals_missing_decision_trails": total - complete_count,
            "decision_trail_completeness": (
                complete_count / total if total else 1.0
            ),
            "decision_trail_issues": issues,
        }

    def runtime_summary(self) -> dict[str, Any]:
        event_health = self.event_store_health()
        task_health = self._task_health()
        proposal_health = self.proposal_health()
        recommendation_health = self.planner_recommendation_health()
        decision_record_health = self.decision_record_health()
        decision_evidence_health = self.decision_evidence_health()
        decision_trail_health = self.decision_trail_health()
        governance_health = self.governance_health()
        evaluation_health = self._evaluation_diagnostics.summary()
        evaluation_reconstruction = self._evaluation_reconstruction_summary()
        task_consistency = self._reconstruction.task_consistency_health()
        proposal_consistency = self._reconstruction.proposal_consistency_health()

        return {
            "decision_record_count": decision_record_health[
                "decision_record_count"
            ],
            "decision_evidence_count": decision_evidence_health[
                "decision_evidence_count"
            ],
            "decision_trail_count": decision_trail_health[
                "proposals_with_decision_trails"
            ],
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
                "source_type_counts": proposal_health["source_type_counts"],
                "unresolved_count": proposal_health["unresolved_count"],
                "inconsistent": proposal_consistency["inconsistent"],
            },
            "planner_recommendations": {
                "planner_recommendation_count": recommendation_health[
                    "total_recommendations"
                ],
                "active_recommendation_count": recommendation_health[
                    "planner_recommendation_status_counts"
                ][PlannerRecommendationStatus.ACTIVE.value],
                "planner_recommendation_promoted_count": recommendation_health[
                    "planner_recommendation_status_counts"
                ][PlannerRecommendationStatus.PROMOTED.value],
                "dismissed_recommendation_count": recommendation_health[
                    "planner_recommendation_status_counts"
                ][PlannerRecommendationStatus.DISMISSED.value],
                "planner_recommendation_unpromoted_count": (
                    recommendation_health[
                        "planner_recommendation_status_counts"
                    ][PlannerRecommendationStatus.ACTIVE.value]
                ),
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
            "evaluations": evaluation_health,
            "evaluation_reconstruction": evaluation_reconstruction,
        }

    @staticmethod
    def _evaluation_reconstruction_summary() -> dict[str, int | str]:
        from app.services.evaluation_reconstruction_service import (
            evaluation_reconstruction_service,
        )

        reconstruction = evaluation_reconstruction_service.inspect()
        return {
            "projections_rebuildable": sum(
                1
                for projection in reconstruction.projections
                if projection.rebuild_supported
            ),
            "successful_reconstructions": (
                reconstruction.successful_reconstructions
            ),
            "failed_reconstructions": reconstruction.failed_reconstructions,
            "replay_validation_status": (
                reconstruction.replay_validation_status
            ),
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
