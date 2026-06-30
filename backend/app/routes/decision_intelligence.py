from fastapi import APIRouter

from app.models.decision_intelligence import DecisionIntelligenceSummary
from app.services.decision_intelligence_service import (
    decision_intelligence_service,
)

router = APIRouter()


@router.get("/runtime/decision-intelligence")
def get_decision_intelligence() -> DecisionIntelligenceSummary:
    return decision_intelligence_service.build()

