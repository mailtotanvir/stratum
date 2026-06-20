from fastapi import APIRouter

from app.models.evaluation_trend_projection import (
    EvaluationTrendBucket,
    EvaluationTrendProjection,
)
from app.services.evaluation_trend_projection_v2_builder_service import (
    evaluation_trend_projection_builder_service,
)
from app.services.evaluation_trend_projection_service import (
    evaluation_trend_projection_service,
)


router = APIRouter()


@router.get("/runtime/evaluation-trend")
def get_evaluation_trend(
    granularity: str | None = None,
) -> EvaluationTrendProjection:
    return evaluation_trend_projection_builder_service.build(
        {"granularity": granularity}
    )


@router.get("/runtime/evaluation-trends")
def list_evaluation_trends(
    target_type: str | None = None,
    session_id: str | None = None,
    decision_id: str | None = None,
    artifact_id: str | None = None,
    evaluation_type: str | None = None,
    status: str | None = None,
    dimension_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    granularity: str | None = None,
) -> list[EvaluationTrendBucket]:
    return evaluation_trend_projection_service.list_trend_buckets(
        target_type=target_type,
        session_id=session_id,
        decision_id=decision_id,
        artifact_id=artifact_id,
        evaluation_type=evaluation_type,
        status=status,
        dimension_id=dimension_id,
        from_date=from_date,
        to_date=to_date,
        granularity=granularity,
    )
