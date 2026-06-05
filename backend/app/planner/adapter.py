from abc import ABC, abstractmethod

from app.models.planner import PlannerRequest, PlannerResponse


class PlannerAdapter(ABC):
    @abstractmethod
    async def plan(self, request: PlannerRequest) -> PlannerResponse:
        pass
