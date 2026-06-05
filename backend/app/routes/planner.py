from fastapi import APIRouter

from app.models.planner import PlannerRequest, PlannerResponse
from app.services.planner_service import planner_service

router = APIRouter()


@router.post("/planner/plan")
async def plan(request: PlannerRequest) -> PlannerResponse:
    return await planner_service.plan(request)
