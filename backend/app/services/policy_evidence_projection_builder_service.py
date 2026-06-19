from datetime import UTC, datetime
from typing import Callable

from app.db.schema import PolicyDecisionRecord, PolicyViolationRecord
from app.models.policy_evidence_projection import (
    PolicyEvidenceItem,
    PolicyEvidenceProjection,
)
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.policy_service import PolicyService, policy_service


POLICY_EVIDENCE_PROJECTION_TYPE = "policy_evidence"
POLICY_EVIDENCE_SCHEMA_VERSION = 1
POLICY_EVIDENCE_SOURCE = "policy_evidence_projection_builder"
POLICY_EVIDENCE_AUTHORITATIVE_SOURCE = (
    "policies/policy_decisions/policy_violations/evaluations"
)


class PolicyEvidenceProjectionBuilderService(
    BaseProjectionBuilder[dict[str, str | None], list[PolicyEvidenceProjection]]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=POLICY_EVIDENCE_PROJECTION_TYPE,
        schema_version=POLICY_EVIDENCE_SCHEMA_VERSION,
        builder_name="PolicyEvidenceProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=POLICY_EVIDENCE_PROJECTION_TYPE,
            reconstruction_source="policy_state",
            authoritative_source=POLICY_EVIDENCE_AUTHORITATIVE_SOURCE,
        ),
    )
    projection_type = POLICY_EVIDENCE_PROJECTION_TYPE

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
    ) -> list[PolicyEvidenceProjection]:
        built_at = self._clock()
        metadata = ProjectionMetadata(
            **self.schema_info.model_dump(),
            built_at=built_at,
            source=POLICY_EVIDENCE_SOURCE,
        )
        projections: list[PolicyEvidenceProjection] = []

        for policy in self._policies.list_policies():
            if source.get("policy_id") not in (None, policy.id):
                continue

            items = [
                item
                for item in self._policy_evidence_items(policy.id)
                if self._matches_filters(item, source)
            ]
            if not items:
                continue

            projections.append(
                PolicyEvidenceProjection(
                    metadata=metadata.model_copy(deep=True),
                    policy_id=policy.id,
                    policy_name=policy.name,
                    policy_type=policy.policy_type,
                    policy_status=policy.status,
                    evidence_count=len(items),
                    decision_evidence_count=sum(
                        1 for item in items if item.evidence_type == "decision"
                    ),
                    violation_evidence_count=sum(
                        1 for item in items if item.evidence_type == "violation"
                    ),
                    evaluation_ids=sorted(
                        {
                            item.evaluation_id
                            for item in items
                            if item.evaluation_id is not None
                        }
                    ),
                    evaluation_result_ids=sorted(
                        {
                            item.evaluation_result_id
                            for item in items
                            if item.evaluation_result_id is not None
                        }
                    ),
                    latest_evidence_at=max(
                        (item.created_at for item in items),
                        default=None,
                    ),
                    evidence_items=items,
                )
            )

        return projections

    def _policy_evidence_items(self, policy_id: str) -> list[PolicyEvidenceItem]:
        items: list[PolicyEvidenceItem] = []
        for decision in self._policies.list_policy_decisions(policy_id):
            if self._has_evaluation_link(decision):
                items.append(self._decision_item(decision))
        for violation in self._policies.list_policy_violations(policy_id):
            if self._has_evaluation_link(violation):
                items.append(self._violation_item(violation))
        return sorted(
            items,
            key=lambda item: (
                item.created_at,
                item.evidence_type,
                item.policy_decision_id or item.policy_violation_id or "",
            ),
        )

    @staticmethod
    def _has_evaluation_link(
        record: PolicyDecisionRecord | PolicyViolationRecord,
    ) -> bool:
        return (
            record.evaluation_id is not None
            or record.evaluation_result_id is not None
        )

    @staticmethod
    def _decision_item(record: PolicyDecisionRecord) -> PolicyEvidenceItem:
        return PolicyEvidenceItem(
            evidence_type="decision",
            policy_decision_id=record.id,
            policy_violation_id=None,
            target_type=record.target_type,
            target_id=record.target_id,
            evaluation_id=record.evaluation_id,
            evaluation_result_id=record.evaluation_result_id,
            decision=record.decision,
            severity=None,
            reason=record.reason,
            message=None,
            created_at=record.created_at.isoformat(),
        )

    @staticmethod
    def _violation_item(record: PolicyViolationRecord) -> PolicyEvidenceItem:
        return PolicyEvidenceItem(
            evidence_type="violation",
            policy_decision_id=None,
            policy_violation_id=record.id,
            target_type=record.target_type,
            target_id=record.target_id,
            evaluation_id=record.evaluation_id,
            evaluation_result_id=record.evaluation_result_id,
            decision=None,
            severity=record.severity,
            reason=None,
            message=record.message,
            created_at=record.created_at.isoformat(),
        )

    @staticmethod
    def _matches_filters(
        item: PolicyEvidenceItem,
        source: dict[str, str | None],
    ) -> bool:
        for field in (
            "evaluation_id",
            "evaluation_result_id",
            "target_type",
            "target_id",
            "evidence_type",
        ):
            expected = source.get(field)
            if expected is not None and getattr(item, field) != expected:
                return False
        return True


policy_evidence_projection_builder_service = (
    PolicyEvidenceProjectionBuilderService()
)
