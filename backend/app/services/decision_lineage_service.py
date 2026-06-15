from app.models.decision_lineage import (
    DecisionLineageChain,
    DecisionLineageEvidence,
    DecisionLineageEvidenceSummary,
    DecisionLineageRecord,
    DecisionLineageSummary,
)
from app.models.runtime_event import EventType
from app.services.decision_lineage_projection_builder_service import (
    DecisionLineageProjectionBuilder,
    decision_lineage_projection_builder,
)
from app.services.event_service import EventService, event_service


class DecisionLineageNotFoundError(LookupError):
    pass


class DecisionLineageService:
    def __init__(
        self,
        builder: DecisionLineageProjectionBuilder | None = None,
        events: EventService | None = None,
    ) -> None:
        self._builder = builder or decision_lineage_projection_builder
        self._events = events or event_service

    def list_records(self) -> list[DecisionLineageRecord]:
        records = self._builder.build_read_only().records
        return list(reversed(records))

    def get_chain(self, decision_id: str) -> DecisionLineageChain:
        records = {
            record.decision_id: record for record in self.list_records()
        }
        target = records.get(decision_id)
        if target is None:
            raise DecisionLineageNotFoundError(
                f"Decision lineage not found: {decision_id}"
            )
        chain = [target]
        visited = {target.decision_id}
        current = target
        complete = not bool(current.metadata.get("orphaned"))
        while current.parent_decision_id is not None:
            parent = records.get(current.parent_decision_id)
            if parent is None or parent.decision_id in visited:
                complete = False
                break
            chain.append(parent)
            visited.add(parent.decision_id)
            current = parent
            complete = complete and not bool(
                current.metadata.get("orphaned")
            )
        chain.reverse()
        return DecisionLineageChain(
            decision_id=decision_id,
            records=chain,
            complete=complete,
        )

    def evidence_summary(
        self,
        decision_id: str,
    ) -> DecisionLineageEvidenceSummary:
        chain = self.get_chain(decision_id)
        record = chain.records[-1]
        evidence = [
            DecisionLineageEvidence(
                evidence_id=str(event.metadata["evidence_id"]),
                evidence_type=_optional_string(
                    event.metadata.get("evidence_type")
                ),
                evidence_reference=_optional_string(
                    event.metadata.get("evidence_reference")
                ),
                summary=_optional_string(event.metadata.get("summary")),
                source_event_id=event.id,
            )
            for event in self._events.list_persisted_events(
                event_type=EventType.DECISION_EVIDENCE_CREATED.value
            )
            if event.metadata.get("decision_id") == decision_id
            and isinstance(event.metadata.get("evidence_id"), str)
            and event.metadata["evidence_id"]
        ]
        evidence.sort(
            key=lambda item: (item.source_event_id, item.evidence_id)
        )
        return DecisionLineageEvidenceSummary(
            decision_id=decision_id,
            evidence_count=len(evidence),
            evidence=evidence,
            related_artifact_ids=record.related_artifact_ids,
        )

    def summary(self) -> DecisionLineageSummary:
        return self._builder.build_read_only().summary


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


decision_lineage_service = DecisionLineageService()
