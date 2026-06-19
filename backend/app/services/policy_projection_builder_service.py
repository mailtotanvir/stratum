from collections import Counter
from datetime import UTC, datetime
from typing import Callable

from app.models.policy_projection import (
    PolicyDecisionSummary,
    PolicySummaryProjection,
    PolicyViolationSummary,
)
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.policy_service import PolicyService, policy_service


POLICY_SUMMARY_PROJECTION_TYPE = "policy_summary"
POLICY_SUMMARY_SCHEMA_VERSION = 1
POLICY_SUMMARY_SOURCE = "policy_projection_builder"
POLICY_SUMMARY_AUTHORITATIVE_SOURCE = (
    "policies/policy_versions/policy_decisions/policy_violations"
)


class PolicyProjectionBuilderService(
    BaseProjectionBuilder[dict[str, str | None], list[PolicySummaryProjection]]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=POLICY_SUMMARY_PROJECTION_TYPE,
        schema_version=POLICY_SUMMARY_SCHEMA_VERSION,
        builder_name="PolicyProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=POLICY_SUMMARY_PROJECTION_TYPE,
            reconstruction_source="policy_state",
            authoritative_source=POLICY_SUMMARY_AUTHORITATIVE_SOURCE,
        ),
    )
    projection_type = POLICY_SUMMARY_PROJECTION_TYPE

    def __init__(
        self,
        policies: PolicyService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._policies = policies or policy_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        source: dict[str, str | None],
    ) -> list[PolicySummaryProjection]:
        policy_type = source.get("policy_type")
        status = source.get("status")
        built_at = self._clock()
        metadata = ProjectionMetadata(
            **self.schema_info.model_dump(),
            built_at=built_at,
            source=POLICY_SUMMARY_SOURCE,
        )
        summaries: list[PolicySummaryProjection] = []

        for policy in self._policies.list_policies():
            if policy_type is not None and policy.policy_type != policy_type:
                continue
            if status is not None and policy.status != status:
                continue

            versions = self._policies.list_policy_versions(policy.id)
            decisions = self._policies.list_policy_decisions(policy.id)
            violations = self._policies.list_policy_violations(policy.id)

            decision_counts = Counter(record.decision for record in decisions)
            violation_counts = Counter(record.severity for record in violations)
            latest_decision_at = max(
                (record.created_at.isoformat() for record in decisions),
                default=None,
            )
            latest_violation_at = max(
                (record.created_at.isoformat() for record in violations),
                default=None,
            )

            summaries.append(
                PolicySummaryProjection(
                    metadata=metadata.model_copy(deep=True),
                    policy_id=policy.id,
                    name=policy.name,
                    description=policy.description,
                    policy_type=policy.policy_type,
                    status=policy.status,
                    latest_version=max(
                        (record.version for record in versions),
                        default=None,
                    ),
                    version_count=len(versions),
                    decision_count=len(decisions),
                    violation_count=len(violations),
                    evaluation_linked_decision_count=sum(
                        1
                        for record in decisions
                        if record.evaluation_id is not None
                        or record.evaluation_result_id is not None
                    ),
                    evaluation_linked_violation_count=sum(
                        1
                        for record in violations
                        if record.evaluation_id is not None
                        or record.evaluation_result_id is not None
                    ),
                    latest_decision_at=latest_decision_at,
                    latest_violation_at=latest_violation_at,
                    decision_summary=[
                        PolicyDecisionSummary(
                            decision=decision,
                            count=decision_counts[decision],
                        )
                        for decision in sorted(decision_counts)
                    ],
                    violation_summary=[
                        PolicyViolationSummary(
                            severity=severity,
                            count=violation_counts[severity],
                        )
                        for severity in sorted(violation_counts)
                    ],
                    created_at=policy.created_at.isoformat(),
                    updated_at=policy.updated_at.isoformat(),
                )
            )

        return summaries


policy_projection_builder_service = PolicyProjectionBuilderService()
