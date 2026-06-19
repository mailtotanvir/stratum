from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db.schema import (
    PolicyDecisionRecord,
    PolicyRecord,
    PolicyVersionRecord,
    PolicyViolationRecord,
)
from app.models.policy_diagnostics import (
    PolicyDiagnostics,
    PolicyProjectionDiagnostics,
)
from app.services.policy_evidence_projection_builder_service import (
    POLICY_EVIDENCE_AUTHORITATIVE_SOURCE,
    POLICY_EVIDENCE_PROJECTION_TYPE,
)
from app.services.policy_evaluation_overview_projection_builder_service import (
    POLICY_EVALUATION_OVERVIEW_AUTHORITATIVE_SOURCE,
    POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE,
)
from app.services.policy_projection_builder_service import (
    POLICY_SUMMARY_AUTHORITATIVE_SOURCE,
    POLICY_SUMMARY_PROJECTION_TYPE,
)
from app.services.policy_service import PolicyService, policy_service
from app.services.projection_registry_service import (
    ProjectionContractNotFoundError,
    ProjectionRegistryService,
    projection_registry_service,
)


POLICY_PROJECTION_SPECS = {
    POLICY_EVIDENCE_PROJECTION_TYPE: {
        "source": POLICY_EVIDENCE_AUTHORITATIVE_SOURCE,
        "route": "/runtime/policy-evidence",
    },
    POLICY_EVALUATION_OVERVIEW_PROJECTION_TYPE: {
        "source": POLICY_EVALUATION_OVERVIEW_AUTHORITATIVE_SOURCE,
        "route": "/runtime/policy-evaluation-overview",
    },
    POLICY_SUMMARY_PROJECTION_TYPE: {
        "source": POLICY_SUMMARY_AUTHORITATIVE_SOURCE,
        "route": "/runtime/policy-projections",
    },
}


class PolicyDiagnosticsService:
    def __init__(
        self,
        policies: PolicyService | None = None,
        projection_registry: ProjectionRegistryService | None = None,
    ) -> None:
        self._policies = policies or policy_service
        self._projection_registry = (
            projection_registry or projection_registry_service
        )

    def generate(self) -> PolicyDiagnostics:
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
            policy_decisions_with_evaluation_count = session.scalar(
                select(func.count())
                .select_from(PolicyDecisionRecord)
                .where(
                    PolicyDecisionRecord.evaluation_id.is_not(None)
                    | PolicyDecisionRecord.evaluation_result_id.is_not(None)
                )
            )
            policy_violations_with_evaluation_count = session.scalar(
                select(func.count())
                .select_from(PolicyViolationRecord)
                .where(
                    PolicyViolationRecord.evaluation_id.is_not(None)
                    | PolicyViolationRecord.evaluation_result_id.is_not(None)
                )
            )
            policies_without_versions_count = session.scalar(
                select(func.count())
                .select_from(PolicyRecord)
                .outerjoin(
                    PolicyVersionRecord,
                    PolicyVersionRecord.policy_id == PolicyRecord.id,
                )
                .where(PolicyVersionRecord.id.is_(None))
            )
            policies_without_decisions_count = session.scalar(
                select(func.count())
                .select_from(PolicyRecord)
                .outerjoin(
                    PolicyDecisionRecord,
                    PolicyDecisionRecord.policy_id == PolicyRecord.id,
                )
                .where(PolicyDecisionRecord.id.is_(None))
            )
            policies_without_violations_count = session.scalar(
                select(func.count())
                .select_from(PolicyRecord)
                .outerjoin(
                    PolicyViolationRecord,
                    PolicyViolationRecord.policy_id == PolicyRecord.id,
                )
                .where(PolicyViolationRecord.id.is_(None))
            )

        projection_types = sorted(POLICY_PROJECTION_SPECS)
        return PolicyDiagnostics(
            policy_count=int(policy_count or 0),
            policy_version_count=int(policy_version_count or 0),
            policy_decision_count=int(policy_decision_count or 0),
            policy_violation_count=int(policy_violation_count or 0),
            policy_decisions_with_evaluation_count=int(
                policy_decisions_with_evaluation_count or 0
            ),
            policy_violations_with_evaluation_count=int(
                policy_violations_with_evaluation_count or 0
            ),
            policies_without_versions_count=int(
                policies_without_versions_count or 0
            ),
            policies_without_decisions_count=int(
                policies_without_decisions_count or 0
            ),
            policies_without_violations_count=int(
                policies_without_violations_count or 0
            ),
            registered_projection_types=[
                projection_type
                for projection_type in projection_types
                if self._projection_registered(projection_type)
            ],
            projections=[
                self._projection_diagnostics(projection_type)
                for projection_type in projection_types
            ],
            generated_at=datetime.now(UTC),
        )

    def _projection_registered(self, projection_type: str) -> bool:
        try:
            self._projection_registry.get(projection_type)
        except ProjectionContractNotFoundError:
            return False
        return True

    def _projection_diagnostics(
        self,
        projection_type: str,
    ) -> PolicyProjectionDiagnostics:
        spec = POLICY_PROJECTION_SPECS[projection_type]
        try:
            detail = self._projection_registry.get(projection_type)
            registered = True
            rebuildable = detail.capabilities.replayable
        except ProjectionContractNotFoundError:
            registered = False
            rebuildable = False

        return PolicyProjectionDiagnostics(
            projection_type=projection_type,
            registered=registered,
            rebuildable=rebuildable,
            persisted=False,
            source=spec["source"],
            route=spec["route"],
        )


policy_diagnostics_service = PolicyDiagnosticsService()
