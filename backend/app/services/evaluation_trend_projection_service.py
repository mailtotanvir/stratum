from app.models.evaluation_trend_projection import EvaluationTrendBucket
from app.services.evaluation_trend_projection_builder_service import (
    EvaluationTrendProjectionBuilderService,
    evaluation_trend_projection_builder_service,
)


class EvaluationTrendProjectionService:
    def __init__(
        self,
        builder: EvaluationTrendProjectionBuilderService | None = None,
    ) -> None:
        self._builder = builder or evaluation_trend_projection_builder_service

    def list_trend_buckets(
        self,
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
        return self._builder.build(
            {
                "target_type": target_type,
                "session_id": session_id,
                "decision_id": decision_id,
                "artifact_id": artifact_id,
                "evaluation_type": evaluation_type,
                "status": status,
                "dimension_id": dimension_id,
                "from_date": from_date,
                "to_date": to_date,
                "granularity": granularity,
            }
        )


evaluation_trend_projection_service = EvaluationTrendProjectionService()
