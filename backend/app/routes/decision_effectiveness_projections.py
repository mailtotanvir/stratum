from fastapi import APIRouter

from app.models.decision_effectiveness_projection import (
    DecisionEffectivenessProjection,
)
from app.services.decision_effectiveness_projection_builder_service import (
    decision_effectiveness_projection_builder_service,
)


router = APIRouter()


@router.get("/runtime/decision-effectiveness")
def list_decision_effectiveness() -> list[DecisionEffectivenessProjection]:
    return decision_effectiveness_projection_builder_service.build()
