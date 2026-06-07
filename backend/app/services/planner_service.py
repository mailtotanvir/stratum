from app.models.planner import PlannerRequest, PlannerResponse
from app.models.runtime_event import EventType
from app.planner.adapter import PlannerAdapter
from app.planner.mock import MockPlannerAdapter
from app.services.event_service import EventService, event_service


class PlannerService:
    def __init__(
        self,
        adapter: PlannerAdapter | None = None,
        events: EventService | None = None,
    ) -> None:
        self._adapter = adapter or MockPlannerAdapter()
        self._events = events or event_service

    async def plan(self, request: PlannerRequest) -> PlannerResponse:
        event_metadata = {
            "task_id": request.task_id,
            "session_id": request.session_id,
            "objective": request.objective,
            "available_tool_count": len(request.available_tools),
        }
        if request.cognitive_state is not None:
            event_metadata.update(
                {
                    "cognitive_health": (
                        request.cognitive_state.cognitive_health.value
                    ),
                    "active_recommendation_count": (
                        request.cognitive_state.active_recommendation_count
                    ),
                    "active_proposal_count": (
                        request.cognitive_state.active_proposal_count
                    ),
                }
            )
        planning_context = request.context.get("planning_context")
        if (
            request.context.get("context_source") == "planning_context"
            and isinstance(planning_context, dict)
        ):
            active_proposals = planning_context.get("active_proposals")
            active_recommendations = planning_context.get(
                "active_recommendations"
            )
            event_metadata.update(
                {
                    "context_source": "planning_context",
                }
            )
            if request.cognitive_state is None:
                event_metadata.update(
                    {
                        "active_proposal_count": (
                            len(active_proposals)
                            if isinstance(active_proposals, list)
                            else 0
                        ),
                        "active_recommendation_count": (
                            len(active_recommendations)
                            if isinstance(active_recommendations, list)
                            else 0
                        ),
                    }
                )

        await self._events.emit_event(
            event_type=EventType.PLANNER_REQUESTED,
            message=f"Planner requested: {request.objective}",
            metadata=event_metadata,
        )

        response = await self._adapter.plan(request)

        await self._events.emit_event(
            event_type=EventType.PLANNER_COMPLETED,
            message="Planner completed",
            metadata={
                "task_id": request.task_id,
                "session_id": request.session_id,
                "proposed_tool_id": (
                    response.proposed_tool.id
                    if response.proposed_tool is not None
                    else None
                ),
                "proposed_tool_name": (
                    response.proposed_tool.name
                    if response.proposed_tool is not None
                    else None
                ),
                "confidence": response.confidence,
            },
        )

        return response


planner_service = PlannerService()
