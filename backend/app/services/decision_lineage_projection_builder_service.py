from collections import defaultdict
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from app.models.decision_lineage import (
    DecisionLineageProjection,
    DecisionLineageRecord,
    DecisionLineageSummary,
)
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.event_service import EventService, event_service


DECISION_LINEAGE_PROJECTION_TYPE = "decision_lineage_projection"
DECISION_LINEAGE_SCHEMA_VERSION = 1
DECISION_LINEAGE_SOURCE = "decision_lineage_projection_builder"

DECISION_LINEAGE_SOURCE_EVENT_TYPES = frozenset(
    {
        EventType.PLANNER_RECOMMENDATION_CREATED,
        EventType.PLANNER_RECOMMENDATION_PROMOTED,
        EventType.PLANNER_RECOMMENDATION_DISMISSED,
        EventType.DECISION_RECORD_CREATED,
        EventType.DECISION_EVIDENCE_CREATED,
        EventType.PROPOSAL_GENERATED,
        EventType.PROPOSAL_RESOLVED,
        EventType.PROPOSAL_ARTIFACT_ATTACHED,
        EventType.ARTIFACT_CREATED,
    }
)


class DecisionLineageProjectionBuilder(
    BaseProjectionBuilder[str, DecisionLineageProjection]
):
    projection_type = DECISION_LINEAGE_PROJECTION_TYPE
    schema_info = ProjectionSchemaInfo(
        projection_type=projection_type,
        schema_version=DECISION_LINEAGE_SCHEMA_VERSION,
        builder_name="DecisionLineageProjectionBuilder",
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

    def build(self, source: str) -> DecisionLineageProjection:
        try:
            projection = self.build_read_only()
        except Exception as exc:
            self._events.emit_event_sync(
                event_type=EventType.DECISION_LINEAGE_RECONSTRUCTION_FAILED,
                severity=Severity.ERROR,
                message=f"Decision lineage reconstruction failed: {exc}",
                metadata={
                    "projection_name": self.projection_type,
                    "projection_version": self.schema_info.schema_version,
                    "source": source,
                    "error_type": type(exc).__name__,
                },
            )
            raise

        self._events.emit_event_sync(
            event_type=EventType.DECISION_LINEAGE_UPDATED,
            message="Decision lineage projection updated",
            metadata={
                "projection_name": self.projection_type,
                "projection_version": self.schema_info.schema_version,
                "record_count": len(projection.records),
                "orphan_count": projection.summary.orphaned_decisions,
            },
        )
        if (
            projection.summary.orphaned_decisions
            or projection.incomplete_event_ids
        ):
            self._events.emit_event_sync(
                event_type=EventType.DECISION_LINEAGE_INCOMPLETE,
                severity=Severity.WARNING,
                message="Decision lineage reconstruction is incomplete",
                metadata={
                    "projection_name": self.projection_type,
                    "projection_version": self.schema_info.schema_version,
                    "orphan_count": projection.summary.orphaned_decisions,
                    "incomplete_event_ids": projection.incomplete_event_ids,
                },
            )
        self._events.emit_event_sync(
            event_type=EventType.DECISION_LINEAGE_REBUILT,
            message="Decision lineage projection rebuilt",
            metadata={
                "projection_name": self.projection_type,
                "projection_version": self.schema_info.schema_version,
                "record_count": len(projection.records),
                "source": source,
            },
        )
        return projection

    def build_read_only(self) -> DecisionLineageProjection:
        events = sorted(
            (
                event
                for event in self._events.list_persisted_events()
                if event.type in DECISION_LINEAGE_SOURCE_EVENT_TYPES
            ),
            key=lambda event: (event.id, event.ts, event.type.value),
        )
        records, incomplete_event_ids = self._records(events)
        return DecisionLineageProjection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=self._clock(),
                source=DECISION_LINEAGE_SOURCE,
            ),
            records=records,
            summary=self._summary(records),
            incomplete_event_ids=incomplete_event_ids,
        )

    def _records(
        self,
        events: list[RuntimeEvent],
    ) -> tuple[list[DecisionLineageRecord], list[int]]:
        recommendations: dict[str, list[RuntimeEvent]] = defaultdict(list)
        proposals: dict[str, list[RuntimeEvent]] = defaultdict(list)
        proposals_by_recommendation: dict[str, set[str]] = defaultdict(set)
        evidence: dict[str, list[RuntimeEvent]] = defaultdict(list)
        artifacts_by_proposal: dict[str, set[str]] = defaultdict(set)
        artifact_events_by_proposal: dict[str, list[RuntimeEvent]] = defaultdict(
            list
        )
        decision_events: list[RuntimeEvent] = []
        incomplete_event_ids: list[int] = []

        for event in events:
            metadata = event.metadata
            if event.type in {
                EventType.PLANNER_RECOMMENDATION_CREATED,
                EventType.PLANNER_RECOMMENDATION_PROMOTED,
                EventType.PLANNER_RECOMMENDATION_DISMISSED,
            }:
                recommendation_id = _string(metadata.get("recommendation_id"))
                if recommendation_id is None:
                    incomplete_event_ids.append(event.id)
                    continue
                recommendations[recommendation_id].append(event)
            elif event.type == EventType.DECISION_RECORD_CREATED:
                if _string(metadata.get("decision_id")) is None:
                    incomplete_event_ids.append(event.id)
                    continue
                decision_events.append(event)
            elif event.type == EventType.DECISION_EVIDENCE_CREATED:
                decision_id = _string(metadata.get("decision_id"))
                if decision_id is None:
                    incomplete_event_ids.append(event.id)
                    continue
                evidence[decision_id].append(event)
            elif event.type in {
                EventType.PROPOSAL_GENERATED,
                EventType.PROPOSAL_RESOLVED,
            }:
                proposal_id = _string(metadata.get("proposal_id"))
                if proposal_id is None:
                    incomplete_event_ids.append(event.id)
                    continue
                proposals[proposal_id].append(event)
                source_id = _string(metadata.get("source_id"))
                if (
                    metadata.get("source_type") == "planner_recommendation"
                    and source_id is not None
                ):
                    proposals_by_recommendation[source_id].add(proposal_id)
            elif event.type == EventType.PROPOSAL_ARTIFACT_ATTACHED:
                proposal_id = _string(metadata.get("proposal_id"))
                artifact_id = _string(metadata.get("artifact_id"))
                if proposal_id is None or artifact_id is None:
                    incomplete_event_ids.append(event.id)
                    continue
                artifacts_by_proposal[proposal_id].add(artifact_id)
                artifact_events_by_proposal[proposal_id].append(event)
            elif event.type == EventType.ARTIFACT_CREATED:
                proposal_id = _string(metadata.get("proposal_id"))
                artifact_id = _string(metadata.get("artifact_id"))
                if proposal_id is not None and artifact_id is not None:
                    artifacts_by_proposal[proposal_id].add(artifact_id)
                    artifact_events_by_proposal[proposal_id].append(event)

        decision_ids = {
            str(event.metadata["decision_id"]) for event in decision_events
        }
        drafts: dict[str, dict[str, Any]] = {}
        for event in decision_events:
            metadata = event.metadata
            decision_id = str(metadata["decision_id"])
            recommendation_id = _recommendation_id(metadata)
            related_proposal_ids = set(
                _string_list(metadata.get("related_proposal_ids"))
            )
            explicit_proposal_id = _string(metadata.get("proposal_id"))
            if explicit_proposal_id is not None:
                related_proposal_ids.add(explicit_proposal_id)
            if recommendation_id is not None:
                related_proposal_ids.update(
                    proposals_by_recommendation.get(recommendation_id, set())
                )
            proposal_ids = sorted(related_proposal_ids)
            parent_decision_id = _string(metadata.get("parent_decision_id"))
            incomplete_reasons: list[str] = []
            if (
                recommendation_id is not None
                and recommendation_id not in recommendations
            ):
                incomplete_reasons.append("missing_recommendation")
            missing_proposals = [
                proposal_id
                for proposal_id in proposal_ids
                if proposal_id not in proposals
            ]
            if missing_proposals:
                incomplete_reasons.append("missing_proposal")
            if (
                parent_decision_id is not None
                and parent_decision_id not in decision_ids
            ):
                incomplete_reasons.append("missing_parent_decision")

            contributing_events = [event]
            if recommendation_id is not None:
                contributing_events.extend(
                    recommendations.get(recommendation_id, [])
                )
            contributing_events.extend(evidence.get(decision_id, []))
            for proposal_id in proposal_ids:
                contributing_events.extend(proposals.get(proposal_id, []))
                contributing_events.extend(
                    artifact_events_by_proposal.get(proposal_id, [])
                )
            source_event_ids = sorted(
                {source_event.id for source_event in contributing_events}
            )
            related_artifact_ids = sorted(
                {
                    artifact_id
                    for proposal_id in proposal_ids
                    for artifact_id in artifacts_by_proposal.get(
                        proposal_id,
                        set(),
                    )
                }
                | set(_string_list(metadata.get("related_artifact_ids")))
            )
            selected_at, timestamp_incomplete = _datetime_value(
                metadata.get("selected_at")
                or metadata.get("created_at"),
                fallback=event.ts,
            )
            if timestamp_incomplete:
                incomplete_reasons.append("invalid_selected_at")
            if (
                metadata.get("related_proposal_ids") is not None
                and not isinstance(
                    metadata.get("related_proposal_ids"),
                    list,
                )
            ):
                incomplete_reasons.append("invalid_related_proposal_ids")
            if (
                metadata.get("related_artifact_ids") is not None
                and not isinstance(
                    metadata.get("related_artifact_ids"),
                    list,
                )
            ):
                incomplete_reasons.append("invalid_related_artifact_ids")
            drafts[decision_id] = {
                "event": event,
                "session_id": _string(metadata.get("session_id")),
                "recommendation_id": recommendation_id,
                "proposal_ids": proposal_ids,
                "parent_decision_id": parent_decision_id,
                "selected_at": selected_at,
                "decision_type": (
                    _string(metadata.get("decision_type")) or "unknown"
                ),
                "outcome": _outcome(
                    recommendation_id,
                    proposal_ids,
                    recommendations,
                    proposals,
                ),
                "evidence_count": len(evidence.get(decision_id, [])),
                "source_event_ids": source_event_ids,
                "related_artifact_ids": related_artifact_ids,
                "incomplete_reasons": incomplete_reasons,
            }

        depths, cyclic_decisions = _lineage_depths(drafts)
        records: list[DecisionLineageRecord] = []
        for decision_id, draft in drafts.items():
            incomplete_reasons = list(draft["incomplete_reasons"])
            if decision_id in cyclic_decisions:
                incomplete_reasons.append("cyclic_parent_lineage")
            event = draft["event"]
            metadata = deepcopy(event.metadata)
            metadata["orphaned"] = bool(incomplete_reasons)
            metadata["incomplete_reasons"] = sorted(set(incomplete_reasons))
            records.append(
                DecisionLineageRecord(
                    decision_id=decision_id,
                    session_id=draft["session_id"],
                    recommendation_id=draft["recommendation_id"],
                    proposal_id=(
                        draft["proposal_ids"][0]
                        if draft["proposal_ids"]
                        else None
                    ),
                    parent_decision_id=draft["parent_decision_id"],
                    lineage_depth=depths[decision_id],
                    selected_at=draft["selected_at"],
                    decision_type=draft["decision_type"],
                    outcome=draft["outcome"],
                    evidence_count=draft["evidence_count"],
                    source_event_ids=draft["source_event_ids"],
                    related_artifact_ids=draft["related_artifact_ids"],
                    related_proposal_ids=draft["proposal_ids"],
                    metadata=metadata,
                )
            )
        records.sort(
            key=lambda record: (
                record.selected_at,
                record.source_event_ids[0],
                record.decision_id,
            )
        )
        return records, sorted(set(incomplete_event_ids))

    def _summary(
        self,
        records: list[DecisionLineageRecord],
    ) -> DecisionLineageSummary:
        orphaned = sum(
            bool(record.metadata.get("orphaned")) for record in records
        )
        evidence_links = sum(record.evidence_count for record in records)
        roots = {_root_id(record, records) for record in records}
        rebuilds = len(
            self._events.list_persisted_events(
                event_type=EventType.DECISION_LINEAGE_REBUILT.value
            )
        )
        return DecisionLineageSummary(
            total_decisions=len(records),
            total_lineage_chains=len(roots),
            average_lineage_depth=round(
                (
                    sum(record.lineage_depth for record in records)
                    / len(records)
                )
                if records
                else 0.0,
                3,
            ),
            orphaned_decisions=orphaned,
            evidence_linked_decisions=sum(
                record.evidence_count > 0 for record in records
            ),
            last_lineage_update=max(
                (record.selected_at for record in records),
                default=None,
            ),
            decision_lineage_records_total=len(records),
            lineage_rebuilds_total=rebuilds,
            lineage_orphans_total=orphaned,
            lineage_max_depth=max(
                (record.lineage_depth for record in records),
                default=0,
            ),
            evidence_links_total=evidence_links,
        )


def _recommendation_id(metadata: dict[str, Any]) -> str | None:
    recommendation_id = _string(metadata.get("recommendation_id"))
    if recommendation_id is not None:
        return recommendation_id
    if metadata.get("selected_entity_type") == "planner_recommendation":
        return _string(metadata.get("selected_entity_id"))
    return None


def _outcome(
    recommendation_id: str | None,
    proposal_ids: list[str],
    recommendations: dict[str, list[RuntimeEvent]],
    proposals: dict[str, list[RuntimeEvent]],
) -> str:
    proposal_outcomes = [
        _string(event.metadata.get("status"))
        for proposal_id in proposal_ids
        for event in proposals.get(proposal_id, [])
        if event.type == EventType.PROPOSAL_RESOLVED
    ]
    if proposal_outcomes:
        return sorted(outcome for outcome in proposal_outcomes if outcome)[-1]
    if recommendation_id is not None:
        recommendation_events = recommendations.get(recommendation_id, [])
        if any(
            event.type == EventType.PLANNER_RECOMMENDATION_DISMISSED
            for event in recommendation_events
        ):
            return "dismissed"
        if any(
            event.type == EventType.PLANNER_RECOMMENDATION_PROMOTED
            for event in recommendation_events
        ):
            return "selected"
    return "selected"


def _lineage_depths(
    drafts: dict[str, dict[str, Any]],
) -> tuple[dict[str, int], set[str]]:
    depths: dict[str, int] = {}
    cyclic: set[str] = set()

    def depth(decision_id: str, path: tuple[str, ...]) -> int:
        if decision_id in depths:
            return depths[decision_id]
        if decision_id in path:
            cyclic.update(path[path.index(decision_id) :])
            return 0
        parent_id = drafts[decision_id]["parent_decision_id"]
        if parent_id is None or parent_id not in drafts:
            result = 0
        else:
            result = depth(parent_id, (*path, decision_id)) + 1
        depths[decision_id] = result
        return result

    for decision_id in sorted(drafts):
        depth(decision_id, ())
    for decision_id in cyclic:
        depths[decision_id] = 0
    return depths, cyclic


def _root_id(
    record: DecisionLineageRecord,
    records: list[DecisionLineageRecord],
) -> str:
    by_id = {candidate.decision_id: candidate for candidate in records}
    current = record
    path: list[str] = []
    while current.parent_decision_id in by_id:
        if current.decision_id in path:
            cycle_start = path.index(current.decision_id)
            return min(path[cycle_start:])
        path.append(current.decision_id)
        current = by_id[current.parent_decision_id]
    return current.decision_id


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(
        {
            item
            for item in value
            if isinstance(item, str) and item
        }
    )


def _datetime_value(
    value: Any,
    *,
    fallback: str,
) -> tuple[datetime, bool]:
    if isinstance(value, datetime):
        return value, False
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ), False
        except ValueError:
            pass
    return datetime.fromisoformat(fallback.replace("Z", "+00:00")), (
        value is not None
    )


decision_lineage_projection_builder = DecisionLineageProjectionBuilder()
