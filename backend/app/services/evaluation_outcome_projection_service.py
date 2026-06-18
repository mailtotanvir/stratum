from app.models.evaluation_outcome_projection import EvaluationOutcomeRollup
from app.services.evaluation_outcome_projection_builder_service import (
    EvaluationOutcomeProjectionBuilderService,
    evaluation_outcome_projection_builder_service,
)


class EvaluationOutcomeRollupNotFoundError(LookupError):
    pass


class EvaluationOutcomeProjectionService:
    def __init__(
        self,
        builder: EvaluationOutcomeProjectionBuilderService | None = None,
    ) -> None:
        self._builder = builder or evaluation_outcome_projection_builder_service

    def list_outcome_rollups(
        self,
        target_type: str | None = None,
        session_id: str | None = None,
        decision_id: str | None = None,
        artifact_id: str | None = None,
        evaluation_type: str | None = None,
        status: str | None = None,
    ) -> list[EvaluationOutcomeRollup]:
        rollups = self._builder.build(
            {
                "session_id": session_id,
                "decision_id": decision_id,
                "artifact_id": artifact_id,
                "evaluation_type": evaluation_type,
                "status": status,
            }
        )
        if target_type is not None:
            rollups = [
                rollup
                for rollup in rollups
                if rollup.target_type == target_type
            ]
        return rollups

    def get_outcome_rollup(
        self,
        target_type: str,
        target_id: str,
    ) -> EvaluationOutcomeRollup:
        matches = [
            rollup
            for rollup in self.list_outcome_rollups(target_type=target_type)
            if rollup.target_id == target_id
        ]
        if not matches:
            raise EvaluationOutcomeRollupNotFoundError(
                "Evaluation outcome rollup not found: "
                f"{target_type}/{target_id}"
            )
        return matches[0]


evaluation_outcome_projection_service = EvaluationOutcomeProjectionService()
