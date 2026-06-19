from app.models.policy_projection import PolicySummaryProjection
from app.services.policy_projection_builder_service import (
    PolicyProjectionBuilderService,
    policy_projection_builder_service,
)


class PolicySummaryNotFoundError(LookupError):
    pass


class PolicyProjectionService:
    def __init__(
        self,
        builder: PolicyProjectionBuilderService | None = None,
    ) -> None:
        self._builder = builder or policy_projection_builder_service

    def list_policy_summaries(
        self,
        policy_type: str | None = None,
        status: str | None = None,
    ) -> list[PolicySummaryProjection]:
        return self._builder.build(
            {
                "policy_type": policy_type,
                "status": status,
            }
        )

    def get_policy_summary(self, policy_id: str) -> PolicySummaryProjection:
        for summary in self.list_policy_summaries():
            if summary.policy_id == policy_id:
                return summary
        raise PolicySummaryNotFoundError(
            f"Policy summary not found: {policy_id}"
        )


policy_projection_service = PolicyProjectionService()
