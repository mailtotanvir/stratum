from app.models.policy_evidence_projection import PolicyEvidenceProjection
from app.services.policy_evidence_projection_builder_service import (
    PolicyEvidenceProjectionBuilderService,
    policy_evidence_projection_builder_service,
)


class PolicyEvidenceNotFoundError(LookupError):
    pass


class PolicyEvidenceProjectionService:
    def __init__(
        self,
        builder: PolicyEvidenceProjectionBuilderService | None = None,
    ) -> None:
        self._builder = builder or policy_evidence_projection_builder_service

    def list_policy_evidence(
        self,
        policy_id: str | None = None,
        evaluation_id: str | None = None,
        evaluation_result_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        evidence_type: str | None = None,
    ) -> list[PolicyEvidenceProjection]:
        return self._builder.build(
            {
                "policy_id": policy_id,
                "evaluation_id": evaluation_id,
                "evaluation_result_id": evaluation_result_id,
                "target_type": target_type,
                "target_id": target_id,
                "evidence_type": evidence_type,
            }
        )

    def get_policy_evidence(
        self,
        policy_id: str,
    ) -> PolicyEvidenceProjection:
        matches = self.list_policy_evidence(policy_id=policy_id)
        if not matches:
            raise PolicyEvidenceNotFoundError(
                f"Policy evidence not found: {policy_id}"
            )
        return matches[0]


policy_evidence_projection_service = PolicyEvidenceProjectionService()
