from app.models.cognitive_state import CognitiveHealth, CognitiveState
from app.models.planning_context import PlanningContext
from app.models.planner import PlannerRecommendationStatus
from app.models.proposal import ProposalStatus
from app.services.decision_evidence_service import (
    DecisionEvidenceService,
    decision_evidence_service,
)
from app.services.decision_record_service import (
    DecisionRecordService,
    decision_record_service,
)
from app.services.diagnostics_service import DiagnosticsService, diagnostics_service
from app.services.planner_recommendation_service import (
    PlannerRecommendationService,
    planner_recommendation_service,
)
from app.services.planning_context_service import (
    PlanningContextService,
    planning_context_service,
)
from app.services.proposal_service import ProposalService, proposal_service
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)


class CognitiveStateService:
    def __init__(
        self,
        planning_context: PlanningContextService | None = None,
        recommendations: PlannerRecommendationService | None = None,
        proposals: ProposalService | None = None,
        decisions: DecisionRecordService | None = None,
        evidence: DecisionEvidenceService | None = None,
        diagnostics: DiagnosticsService | None = None,
        sessions: RuntimeSessionService | None = None,
    ) -> None:
        self._planning_context = planning_context or planning_context_service
        self._recommendations = recommendations or planner_recommendation_service
        self._proposals = proposals or proposal_service
        self._decisions = decisions or decision_record_service
        self._evidence = evidence or decision_evidence_service
        self._diagnostics = diagnostics or diagnostics_service
        self._sessions = sessions or runtime_session_service

    def build(
        self,
        session_id: str,
        planning_context: PlanningContext | None = None,
    ) -> CognitiveState:
        session = self._sessions.get_session(session_id)
        current_planning_context = (
            planning_context or self._planning_context.build(session_id)
        )
        recommendations = self._recommendations.list_recommendations(session_id)
        proposals = self._proposals.list_proposals(task_id=session.task_id)
        decisions = self._decisions.list_decision_records(session_id)
        decision_ids = {record.decision_id for record in decisions}
        evidence = [
            record
            for record in self._evidence.list_evidence()
            if record.decision_id in decision_ids
        ]

        return CognitiveState(
            session_id=session.id,
            task_id=session.task_id,
            active_recommendation_count=self._count_recommendations(
                recommendations,
                PlannerRecommendationStatus.ACTIVE,
            ),
            promoted_recommendation_count=self._count_recommendations(
                recommendations,
                PlannerRecommendationStatus.PROMOTED,
            ),
            dismissed_recommendation_count=self._count_recommendations(
                recommendations,
                PlannerRecommendationStatus.DISMISSED,
            ),
            active_proposal_count=sum(
                1
                for proposal in proposals
                if proposal.status == ProposalStatus.PROPOSED.value
            ),
            decision_record_count=len(decisions),
            decision_evidence_count=len(evidence),
            latest_recommendation_id=self._latest_id(recommendations, "id"),
            latest_decision_id=self._latest_id(decisions, "decision_id"),
            latest_proposal_id=self._latest_id(proposals, "id"),
            available_tool_count=len(current_planning_context.available_tools),
            cognitive_health=(
                CognitiveHealth.HEALTHY
                if (
                    current_planning_context.diagnostics_summary.governance_status
                    == "ok"
                )
                else CognitiveHealth.DEGRADED
            ),
        )

    def reconstruct(self, session_id: str) -> CognitiveState:
        return self.build(session_id)

    def diagnostics(self) -> dict[str, object]:
        states = [
            self.build(session.id)
            for session in self._sessions.list_sessions()
        ]
        distribution = {
            CognitiveHealth.HEALTHY.value: 0,
            CognitiveHealth.DEGRADED.value: 0,
        }
        for state in states:
            distribution[state.cognitive_health.value] += 1
        return {
            "cognitive_state_generated_count": len(states),
            "cognitive_health_distribution": distribution,
        }

    def _count_recommendations(
        self,
        recommendations: list,
        status: PlannerRecommendationStatus,
    ) -> int:
        return sum(
            1 for record in recommendations if record.status == status.value
        )

    def _latest_id(self, records: list, id_field: str) -> str | None:
        if not records:
            return None
        latest = max(
            records,
            key=lambda record: (
                record.created_at,
                getattr(record, id_field),
            ),
        )
        return getattr(latest, id_field)


cognitive_state_service = CognitiveStateService()


def get_session_cognitive_state(session_id: str) -> CognitiveState:
    return cognitive_state_service.build(session_id)
