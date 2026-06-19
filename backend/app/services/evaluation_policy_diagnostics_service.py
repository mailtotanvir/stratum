from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db.schema import (
    EvaluationRecord,
    EvaluationResultRecord,
    PolicyDecisionRecord,
    PolicyRecord,
    PolicyVersionRecord,
    PolicyViolationRecord,
)
from app.models.evaluation_policy_diagnostics import (
    EvaluationPolicyDiagnostics,
)
from app.services.evaluation_service import EvaluationService, evaluation_service
from app.services.policy_service import PolicyService, policy_service
from app.services.projection_registry_service import (
    ProjectionContractNotFoundError,
    ProjectionRegistryService,
    projection_registry_service,
)


EXPECTED_EVALUATION_PROJECTION_TYPES = [
    "evaluation_outcome_rollup",
    "evaluation_summary",
    "evaluation_trend",
]
EXPECTED_POLICY_PROJECTION_TYPES = [
    "policy_evaluation_overview",
    "policy_evidence",
    "policy_summary",
]
EXPECTED_EVALUATION_POLICY_PROJECTION_TYPES = sorted(
    EXPECTED_EVALUATION_PROJECTION_TYPES + EXPECTED_POLICY_PROJECTION_TYPES
)


class EvaluationPolicyDiagnosticsService:
    def __init__(
        self,
        evaluations: EvaluationService | None = None,
        policies: PolicyService | None = None,
        projection_registry: ProjectionRegistryService | None = None,
    ) -> None:
        self._evaluations = evaluations or evaluation_service
        self._policies = policies or policy_service
        self._projection_registry = (
            projection_registry or projection_registry_service
        )

    def generate(self) -> EvaluationPolicyDiagnostics:
        with self._evaluations.session_factory() as session:
            evaluation_count = session.scalar(
                select(func.count()).select_from(EvaluationRecord)
            )
            evaluation_result_count = session.scalar(
                select(func.count()).select_from(EvaluationResultRecord)
            )
            persisted_evaluation_ids = set(
                session.scalars(select(EvaluationRecord.id)).all()
            )
            result_evaluation_ids = {
                result_id: evaluation_id
                for result_id, evaluation_id in session.execute(
                    select(
                        EvaluationResultRecord.id,
                        EvaluationResultRecord.evaluation_id,
                    )
                ).all()
            }

        with self._policies.session_factory() as session:
            policy_count = session.scalar(
                select(func.count()).select_from(PolicyRecord)
            )
            policy_version_count = session.scalar(
                select(func.count()).select_from(PolicyVersionRecord)
            )
            policy_decision_count = session.scalar(
                select(func.count()).select_from(PolicyDecisionRecord)
            )
            policy_violation_count = session.scalar(
                select(func.count()).select_from(PolicyViolationRecord)
            )
            linked_decisions = session.scalars(
                select(PolicyDecisionRecord).where(
                    PolicyDecisionRecord.evaluation_id.is_not(None)
                    | PolicyDecisionRecord.evaluation_result_id.is_not(None)
                )
            ).all()
            linked_violations = session.scalars(
                select(PolicyViolationRecord).where(
                    PolicyViolationRecord.evaluation_id.is_not(None)
                    | PolicyViolationRecord.evaluation_result_id.is_not(None)
                )
            ).all()

        linked_evaluation_ids: set[str] = set()
        for record in [*linked_decisions, *linked_violations]:
            linked_evaluation_ids.update(
                self._valid_linked_evaluation_ids(
                    evaluation_id=record.evaluation_id,
                    evaluation_result_id=record.evaluation_result_id,
                    persisted_evaluation_ids=persisted_evaluation_ids,
                    result_evaluation_ids=result_evaluation_ids,
                )
            )

        registered_evaluation_projection_types = [
            projection_type
            for projection_type in EXPECTED_EVALUATION_PROJECTION_TYPES
            if self._projection_registered(projection_type)
        ]
        registered_policy_projection_types = [
            projection_type
            for projection_type in EXPECTED_POLICY_PROJECTION_TYPES
            if self._projection_registered(projection_type)
        ]
        registered_projection_types = set(
            registered_evaluation_projection_types
            + registered_policy_projection_types
        )

        return EvaluationPolicyDiagnostics(
            evaluation_count=int(evaluation_count or 0),
            evaluation_result_count=int(evaluation_result_count or 0),
            policy_count=int(policy_count or 0),
            policy_version_count=int(policy_version_count or 0),
            policy_decision_count=int(policy_decision_count or 0),
            policy_violation_count=int(policy_violation_count or 0),
            linked_policy_decision_count=len(linked_decisions),
            linked_policy_violation_count=len(linked_violations),
            linked_evaluation_count=len(linked_evaluation_ids),
            unlinked_evaluation_count=(
                len(persisted_evaluation_ids) - len(linked_evaluation_ids)
            ),
            registered_evaluation_projection_types=(
                registered_evaluation_projection_types
            ),
            registered_policy_projection_types=registered_policy_projection_types,
            missing_expected_projection_types=[
                projection_type
                for projection_type in EXPECTED_EVALUATION_POLICY_PROJECTION_TYPES
                if projection_type not in registered_projection_types
            ],
            generated_at=datetime.now(UTC),
        )

    def _projection_registered(self, projection_type: str) -> bool:
        try:
            self._projection_registry.get(projection_type)
        except ProjectionContractNotFoundError:
            return False
        return True

    @staticmethod
    def _valid_linked_evaluation_ids(
        evaluation_id: str | None,
        evaluation_result_id: str | None,
        persisted_evaluation_ids: set[str],
        result_evaluation_ids: dict[str, str],
    ) -> set[str]:
        linked_ids: set[str] = set()
        if evaluation_id in persisted_evaluation_ids:
            linked_ids.add(evaluation_id)
        if evaluation_result_id in result_evaluation_ids:
            linked_ids.add(result_evaluation_ids[evaluation_result_id])
        return linked_ids


evaluation_policy_diagnostics_service = EvaluationPolicyDiagnosticsService()
