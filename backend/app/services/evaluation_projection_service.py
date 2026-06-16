from app.models.evaluation_projection import EvaluationSummaryProjection
from app.services.evaluation_projection_builder_service import (
    EvaluationProjectionBuilderService,
    evaluation_projection_builder_service,
)


class EvaluationSummaryProjectionNotFoundError(LookupError):
    pass


class EvaluationProjectionService:
    def __init__(
        self,
        builder: EvaluationProjectionBuilderService | None = None,
    ) -> None:
        self._builder = builder or evaluation_projection_builder_service

    def list_evaluation_summaries(
        self,
        session_id: str | None = None,
        decision_id: str | None = None,
        artifact_id: str | None = None,
        evaluation_type: str | None = None,
        status: str | None = None,
    ) -> list[EvaluationSummaryProjection]:
        return self._builder.build(
            {
                "session_id": session_id,
                "decision_id": decision_id,
                "artifact_id": artifact_id,
                "evaluation_type": evaluation_type,
                "status": status,
            }
        )

    def get_evaluation_summary(
        self,
        evaluation_id: str,
    ) -> EvaluationSummaryProjection:
        matches = [
            projection
            for projection in self.list_evaluation_summaries()
            if projection.evaluation_id == evaluation_id
        ]
        if not matches:
            raise EvaluationSummaryProjectionNotFoundError(
                f"Evaluation summary projection not found: {evaluation_id}"
            )
        return matches[0]


evaluation_projection_service = EvaluationProjectionService()
