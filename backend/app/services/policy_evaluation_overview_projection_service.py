from app.models.policy_evaluation_overview_projection import (
    PolicyEvaluationOverviewProjection,
)
from app.services.policy_evaluation_overview_projection_builder_service import (
    PolicyEvaluationOverviewProjectionBuilderService,
    policy_evaluation_overview_projection_builder_service,
)


class PolicyEvaluationOverviewProjectionService:
    def __init__(
        self,
        builder: PolicyEvaluationOverviewProjectionBuilderService | None = None,
    ) -> None:
        self._builder = (
            builder or policy_evaluation_overview_projection_builder_service
        )

    def get_policy_evaluation_overview(
        self,
    ) -> list[PolicyEvaluationOverviewProjection]:
        return self._builder.build({})


policy_evaluation_overview_projection_service = (
    PolicyEvaluationOverviewProjectionService()
)
