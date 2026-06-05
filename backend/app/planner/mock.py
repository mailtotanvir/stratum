from app.models.planner import PlannerRequest, PlannerResponse
from app.planner.adapter import PlannerAdapter


class MockPlannerAdapter(PlannerAdapter):
    async def plan(self, request: PlannerRequest) -> PlannerResponse:
        for tool in request.available_tools:
            if tool.enabled:
                return PlannerResponse(
                    proposed_tool=tool,
                    rationale=f"Selected first enabled tool: {tool.name}",
                    confidence=0.75,
                )

        return PlannerResponse(
            proposed_tool=None,
            rationale="No enabled tools available for planning.",
            confidence=0.0,
        )
