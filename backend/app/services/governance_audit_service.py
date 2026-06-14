from app.models.governance_audit import (
    GovernanceAuditRecord,
    GovernanceAuditSummary,
)
from app.services.governance_audit_projection_builder_service import (
    GovernanceAuditProjectionBuilder,
    governance_audit_projection_builder,
)


class GovernanceAuditRecordNotFoundError(LookupError):
    pass


class GovernanceAuditService:
    def __init__(
        self,
        builder: GovernanceAuditProjectionBuilder | None = None,
    ) -> None:
        self._builder = builder or governance_audit_projection_builder

    def list_records(self) -> list[GovernanceAuditRecord]:
        projection = self._builder.build_read_only()
        return list(reversed(projection.records))

    def get_record(self, decision_id: str) -> GovernanceAuditRecord:
        record = next(
            (
                candidate
                for candidate in self.list_records()
                if candidate.decision_id == decision_id
            ),
            None,
        )
        if record is None:
            raise GovernanceAuditRecordNotFoundError(
                f"Governance audit record not found: {decision_id}"
            )
        return record

    def summary(self) -> GovernanceAuditSummary:
        return self._builder.build_read_only().summary


governance_audit_service = GovernanceAuditService()
