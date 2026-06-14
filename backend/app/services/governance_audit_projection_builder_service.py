from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from app.models.governance_audit import (
    GovernanceAuditProjection,
    GovernanceAuditRecord,
    GovernanceAuditSummary,
)
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.models.runtime_event import EventType, RuntimeEvent
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.event_service import EventService, event_service


GOVERNANCE_AUDIT_PROJECTION_TYPE = "governance_audit_projection"
GOVERNANCE_AUDIT_SCHEMA_VERSION = 1
GOVERNANCE_AUDIT_SOURCE = "governance_audit_projection_builder"

GOVERNANCE_SOURCE_EVENT_TYPES = frozenset(
    {
        EventType.RUNTIME_GOVERNANCE_WARNING,
        EventType.RUNTIME_GOVERNANCE_BLOCKED,
        EventType.TOOL_EXECUTION_GOVERNANCE_WARNING,
        EventType.TOOL_EXECUTION_GOVERNANCE_BLOCKED,
        EventType.DECISION_RECORD_CREATED,
        EventType.PLANNER_RECOMMENDATION_PROMOTED,
        EventType.PLANNER_RECOMMENDATION_DISMISSED,
        EventType.PROPOSAL_RESOLVED,
        EventType.REFLECTION_REQUESTED,
        EventType.REFLECTION_RESOLVED,
    }
)


class GovernanceAuditProjectionBuildError(ValueError):
    pass


class GovernanceAuditProjectionBuilder(
    BaseProjectionBuilder[str, GovernanceAuditProjection]
):
    projection_type = GOVERNANCE_AUDIT_PROJECTION_TYPE
    schema_info = ProjectionSchemaInfo(
        projection_type=projection_type,
        schema_version=GOVERNANCE_AUDIT_SCHEMA_VERSION,
        builder_name="GovernanceAuditProjectionBuilder",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=projection_type,
            reconstruction_source="runtime_event_store",
            authoritative_source="runtime_event_store",
        ),
    )

    def __init__(
        self,
        events: EventService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._events = events or event_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(self, source: str) -> GovernanceAuditProjection:
        projection = self.build_read_only()
        for record in projection.records:
            self._events.emit_event_sync(
                event_type=EventType.GOVERNANCE_DECISION_RECORDED,
                message="Governance decision recorded",
                metadata={
                    "decision_id": record.decision_id,
                    "decision_type": record.decision_type,
                    "source_event_id": record.source_event_id,
                    "outcome": record.outcome,
                },
            )
        self._events.emit_event_sync(
            event_type=EventType.GOVERNANCE_PROJECTION_UPDATED,
            message="Governance audit projection updated",
            metadata={
                "projection_name": self.projection_type,
                "projection_version": self.schema_info.schema_version,
                "record_count": len(projection.records),
            },
        )
        self._events.emit_event_sync(
            event_type=EventType.GOVERNANCE_PROJECTION_REBUILT,
            message="Governance audit projection rebuilt",
            metadata={
                "projection_name": self.projection_type,
                "projection_version": self.schema_info.schema_version,
                "record_count": len(projection.records),
                "source": source,
            },
        )
        return projection

    def build_read_only(self) -> GovernanceAuditProjection:
        source_events = [
            event
            for event in self._events.list_persisted_events()
            if event.type in GOVERNANCE_SOURCE_EVENT_TYPES
        ]
        evidence_counts = Counter(
            str(event.metadata["decision_id"])
            for event in self._events.list_persisted_events(
                event_type=EventType.DECISION_EVIDENCE_CREATED.value
            )
            if isinstance(event.metadata.get("decision_id"), str)
        )
        records = [
            self._record_for_event(event, evidence_counts)
            for event in source_events
        ]
        records.sort(
            key=lambda record: (
                record.occurred_at,
                record.source_event_id,
                record.decision_id,
            )
        )
        return GovernanceAuditProjection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=self._clock(),
                source=GOVERNANCE_AUDIT_SOURCE,
            ),
            records=records,
            summary=_summary(records),
        )

    def _record_for_event(
        self,
        event: RuntimeEvent,
        evidence_counts: Counter[str],
    ) -> GovernanceAuditRecord:
        metadata = event.metadata
        if event.type in {
            EventType.RUNTIME_GOVERNANCE_WARNING,
            EventType.RUNTIME_GOVERNANCE_BLOCKED,
        }:
            decision_id = _required_string(metadata, "task_id", event)
            outcome = _required_string(metadata, "decision", event)
            return self._record(
                event,
                decision_id=f"runtime-policy:{decision_id}:{event.id}",
                decision_type="policy_evaluation",
                session_id=_optional_string(metadata, "session_id"),
                actor="runtime",
                outcome=outcome,
                evidence_count=0,
                policy_reference="runtime_governance_policy",
                budget_reference=_budget_reference(metadata),
            )

        if event.type in {
            EventType.TOOL_EXECUTION_GOVERNANCE_WARNING,
            EventType.TOOL_EXECUTION_GOVERNANCE_BLOCKED,
        }:
            invocation_id = _required_string(
                metadata,
                "tool_invocation_id",
                event,
            )
            return self._record(
                event,
                decision_id=f"tool-policy:{invocation_id}:{event.id}",
                decision_type="policy_evaluation",
                session_id=_required_string(
                    metadata,
                    "session_id",
                    event,
                ),
                actor="tool_execution",
                outcome=_required_string(metadata, "decision", event),
                evidence_count=0,
                policy_reference="tool_execution_governance_policy",
                budget_reference=_budget_reference(metadata),
            )

        if event.type == EventType.DECISION_RECORD_CREATED:
            decision_id = _required_string(
                metadata,
                "decision_id",
                event,
            )
            return self._record(
                event,
                decision_id=decision_id,
                decision_type=_required_string(
                    metadata,
                    "decision_type",
                    event,
                ),
                session_id=_required_string(
                    metadata,
                    "session_id",
                    event,
                ),
                actor="runtime_operator",
                outcome="selected",
                evidence_count=evidence_counts[decision_id],
                policy_reference=_optional_string(
                    metadata,
                    "policy_reference",
                ),
            )

        if event.type in {
            EventType.PLANNER_RECOMMENDATION_PROMOTED,
            EventType.PLANNER_RECOMMENDATION_DISMISSED,
        }:
            recommendation_id = _required_string(
                metadata,
                "recommendation_id",
                event,
            )
            outcome = (
                "selected"
                if event.type
                == EventType.PLANNER_RECOMMENDATION_PROMOTED
                else "dismissed"
            )
            return self._record(
                event,
                decision_id=f"recommendation:{recommendation_id}:{event.id}",
                decision_type="recommendation_selection",
                session_id=_required_string(
                    metadata,
                    "session_id",
                    event,
                ),
                actor="planner_selection",
                outcome=outcome,
                evidence_count=0,
                policy_reference=_optional_string(
                    metadata,
                    "governance_status",
                ),
            )

        if event.type == EventType.PROPOSAL_RESOLVED:
            proposal_id = _required_string(
                metadata,
                "proposal_id",
                event,
            )
            status = _required_string(metadata, "status", event)
            if status not in {"approved", "rejected"}:
                raise GovernanceAuditProjectionBuildError(
                    f"Malformed governance event {event.id}: "
                    "proposal status must be approved or rejected"
                )
            return self._record(
                event,
                decision_id=f"proposal:{proposal_id}",
                decision_type=(
                    "proposal_approval"
                    if status == "approved"
                    else "proposal_rejection"
                ),
                session_id=_optional_string(metadata, "session_id"),
                actor="governance_operator",
                outcome=status,
                evidence_count=0,
                policy_reference=_optional_string(
                    metadata,
                    "source_type",
                ),
            )

        reflection_id = _required_string(
            metadata,
            "reflection_request_id",
            event,
        )
        return self._record(
            event,
            decision_id=f"reflection:{reflection_id}:{event.id}",
            decision_type="reflection_trigger",
            session_id=_optional_string(metadata, "session_id"),
            actor="runtime_reflection",
            outcome=(
                "triggered"
                if event.type == EventType.REFLECTION_REQUESTED
                else "resolved"
            ),
            evidence_count=0,
            reflection_reference=reflection_id,
        )

    @staticmethod
    def _record(
        event: RuntimeEvent,
        *,
        decision_id: str,
        decision_type: str,
        session_id: str | None,
        actor: str,
        outcome: str,
        evidence_count: int,
        policy_reference: str | None = None,
        budget_reference: str | None = None,
        reflection_reference: str | None = None,
    ) -> GovernanceAuditRecord:
        return GovernanceAuditRecord(
            decision_id=decision_id,
            decision_type=decision_type,
            session_id=session_id,
            source_event_id=event.id,
            occurred_at=event.ts,
            actor=actor,
            outcome=outcome,
            evidence_count=evidence_count,
            policy_reference=policy_reference,
            budget_reference=budget_reference,
            reflection_reference=reflection_reference,
            metadata=deepcopy(event.metadata),
        )


def _required_string(
    metadata: dict[str, Any],
    field: str,
    event: RuntimeEvent,
) -> str:
    value = metadata.get(field)
    if not isinstance(value, str) or not value:
        raise GovernanceAuditProjectionBuildError(
            f"Malformed governance event {event.id}: "
            f"missing {field}"
        )
    return value


def _optional_string(
    metadata: dict[str, Any],
    field: str,
) -> str | None:
    value = metadata.get(field)
    return value if isinstance(value, str) and value else None


def _budget_reference(metadata: dict[str, Any]) -> str | None:
    reasons = metadata.get("reasons")
    if isinstance(reasons, list) and any(
        isinstance(reason, str) and "budget" in reason
        for reason in reasons
    ):
        return "default_error_budget_policy"
    return _optional_string(metadata, "budget_reference")


def _summary(
    records: list[GovernanceAuditRecord],
) -> GovernanceAuditSummary:
    approvals = sum(record.outcome == "approved" for record in records)
    rejections = sum(record.outcome == "rejected" for record in records)
    policy_evaluations = sum(
        record.decision_type == "policy_evaluation"
        for record in records
    )
    reflection_triggers = sum(
        record.decision_type == "reflection_trigger"
        and record.outcome == "triggered"
        for record in records
    )
    budget_actions = sum(
        record.budget_reference is not None for record in records
    )
    last_activity = max(
        (record.occurred_at for record in records),
        default=None,
    )
    return GovernanceAuditSummary(
        total_decisions=len(records),
        approvals=approvals,
        rejections=rejections,
        policy_evaluations=policy_evaluations,
        reflection_triggers=reflection_triggers,
        budget_actions=budget_actions,
        last_governance_activity_timestamp=last_activity,
        governance_records_total=len(records),
        approvals_total=approvals,
        rejections_total=rejections,
        policy_evaluations_total=policy_evaluations,
        reflection_triggers_total=reflection_triggers,
        budget_actions_total=budget_actions,
    )


governance_audit_projection_builder = GovernanceAuditProjectionBuilder()
