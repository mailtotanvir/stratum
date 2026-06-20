from fastapi import APIRouter

from app.models.recommendation_outcome_projection import (
    RecommendationOutcomeProjection,
)
from app.services.recommendation_outcome_projection_builder_service import (
    recommendation_outcome_projection_builder_service,
)


router = APIRouter()


@router.get("/runtime/recommendation-outcomes")
def list_recommendation_outcomes() -> list[RecommendationOutcomeProjection]:
    return recommendation_outcome_projection_builder_service.build()
