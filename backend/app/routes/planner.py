from fastapi import APIRouter, HTTPException

from app.models.planner import PlannerPlanRequest, PlannerResponse
from app.services.planner_input_builder_service import planner_input_builder_service
from app.services.planner_service import planner_service
from app.services.runtime_session_service import RuntimeSessionNotFoundError

router = APIRouter()


@router.post("/planner/plan")
async def plan(request: PlannerPlanRequest) -> PlannerResponse:
    try:
        planner_request = await planner_input_builder_service.build(
            request.session_id,
            request.objective,
        )
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await planner_service.plan(planner_request)
