from typing import Any

from app.models.planning_context import (
    PlanningContext,
    PlanningDiagnosticsSummary,
    PlanningEventSummary,
    PlanningProposalSummary,
    PlanningRecommendationSummary,
)
from app.models.planning_context_snapshot import (
    PLANNING_CONTEXT_SNAPSHOT_VERSION,
)
from app.models.planner import PlannerRecommendationStatus
from app.models.proposal import ProposalSourceType, ProposalStatus
from app.models.tool import Tool, ToolParameter
from app.services.diagnostics_service import DiagnosticsService, diagnostics_service
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
from app.services.tool_registry_service import (
    ToolRegistryService,
    tool_registry_service,
)


DEFAULT_RECENT_EVENT_LIMIT = 20


class PlanningContextService:
    def __init__(
        self,
        sessions: RuntimeSessionService | None = None,
        proposals: ProposalService | None = None,
        recommendations: PlannerRecommendationService | None = None,
        tools: ToolRegistryService | None = None,
        diagnostics: DiagnosticsService | None = None,
        events: EventService | None = None,
        recent_event_limit: int = DEFAULT_RECENT_EVENT_LIMIT,
    ) -> None:
        self._sessions = sessions or runtime_session_service
        self._proposals = proposals or proposal_service
        self._recommendations = recommendations or planner_recommendation_service
        self._tools = tools or tool_registry_service
        self._diagnostics = diagnostics or diagnostics_service
        self._events = events or event_service
        self._recent_event_limit = recent_event_limit

    def build(self, session_id: str) -> PlanningContext:
        runtime_session = self._sessions.get_session(session_id)
        proposal_records = sorted(
            self._proposals.list_proposals(
                status=ProposalStatus.PROPOSED.value,
                task_id=runtime_session.task_id,
            ),
            key=lambda record: (record.created_at, record.id),
        )
        task_proposals = self._proposals.list_proposals(
            task_id=runtime_session.task_id
        )
        promoted_recommendation_ids = {
            record.source_id
            for record in task_proposals
            if (
                record.source_type
                == ProposalSourceType.PLANNER_RECOMMENDATION.value
                and record.source_id is not None
            )
        }
        recommendation_records = sorted(
            (
                record
                for record in self._recommendations.list_recommendations(
                    session_id,
                    status=PlannerRecommendationStatus.ACTIVE.value,
                )
                if record.id not in promoted_recommendation_ids
            ),
            key=lambda record: (record.created_at, record.id),
        )
        tool_records = sorted(
            self._tools.list_tools(enabled_only=True),
            key=lambda record: (record.name, record.id),
        )
        recent_events = self._events.list_persisted_events(
            task_id=runtime_session.task_id,
            limit=self._recent_event_limit,
        )

        proposals = [
            PlanningProposalSummary(
                id=record.id,
                title=record.title,
                status=record.status,
                source_type=record.source_type,
                source_id=record.source_id,
                created_at=record.created_at.isoformat(),
            )
            for record in proposal_records
        ]
        recommendations = [
            PlanningRecommendationSummary(
                id=record.id,
                objective=record.objective,
                proposed_tool=self._recommendations.proposed_tool_for(record),
                rationale=record.rationale,
                confidence=record.confidence,
                governance_status=record.governance_status,
                created_at=record.created_at.isoformat(),
            )
            for record in recommendation_records
        ]
        available_tools = [self._to_tool(record) for record in tool_records]
        event_summaries = [
            PlanningEventSummary(
                id=event.id,
                timestamp=event.ts,
                type=event.type.value,
                severity=event.severity.value,
                message=event.message,
                metadata=event.metadata,
            )
            for event in recent_events
        ]
        governance_health = self._diagnostics.governance_health()

        return PlanningContext(
            session_id=runtime_session.id,
            task_id=runtime_session.task_id,
            active_proposals=proposals,
            active_recommendations=recommendations,
            available_tools=available_tools,
            recent_events=event_summaries,
            diagnostics_summary=PlanningDiagnosticsSummary(
                proposal_count=len(proposals),
                recommendation_count=len(recommendations),
                available_tool_count=len(available_tools),
                event_count=len(event_summaries),
                latest_event_type=(
                    event_summaries[-1].type if event_summaries else None
                ),
                governance_status=governance_health["status"],
                highest_severity=governance_health["highest_severity"],
                has_critical=governance_health["has_critical"],
            ),
        )

    def compact_snapshot(
        self,
        planning_context: PlanningContext,
    ) -> dict[str, Any]:
        return {
            "schema_version": PLANNING_CONTEXT_SNAPSHOT_VERSION,
            "active_proposal_count": len(planning_context.active_proposals),
            "active_recommendation_count": len(
                planning_context.active_recommendations
            ),
            "available_tool_count": len(planning_context.available_tools),
            "recent_event_count": len(planning_context.recent_events),
            "diagnostics_summary": (
                planning_context.diagnostics_summary.model_dump(mode="json")
            ),
        }

    def _to_tool(self, record) -> Tool:
        return Tool(
            id=record.id,
            name=record.name,
            description=record.description,
            enabled=record.enabled,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
            parameters=[
                ToolParameter(
                    id=parameter.id,
                    tool_id=parameter.tool_id,
                    name=parameter.name,
                    type=parameter.type,
                    required=parameter.required,
                )
                for parameter in self._tools.list_parameters(record.id)
            ],
        )


planning_context_service = PlanningContextService()
