from fastapi import APIRouter

from app.models.evaluation_intelligence_overview import (
    EvaluationIntelligenceOverviewProjection,
)
from app.services.evaluation_intelligence_overview_projection_builder_service import (
    evaluation_intelligence_overview_projection_builder_service,
)


router = APIRouter()


@router.get("/evaluation-intelligence-overview")
def get_evaluation_intelligence_overview() -> (
    EvaluationIntelligenceOverviewProjection
):
    return evaluation_intelligence_overview_projection_builder_service.build()


@router.get("/evaluation-intelligence-overview/projection")
def get_evaluation_intelligence_overview_projection() -> (
    EvaluationIntelligenceOverviewProjection
):
    return evaluation_intelligence_overview_projection_builder_service.build()
