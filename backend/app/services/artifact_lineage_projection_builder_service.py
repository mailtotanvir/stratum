from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.models.artifact_lineage import (
    ArtifactLineageProjection,
    ArtifactLineageRecord,
    ArtifactLineageSummary,
)
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.event_service import EventService, event_service


ARTIFACT_LINEAGE_PROJECTION_TYPE = "artifact_lineage_projection"
ARTIFACT_LINEAGE_SCHEMA_VERSION = 1
ARTIFACT_LINEAGE_SOURCE = "artifact_lineage_projection_builder"

ARTIFACT_LINEAGE_SOURCE_EVENT_TYPES = frozenset(
    {
        EventType.ARTIFACT_CREATED,
        EventType.RUNTIME_ARTIFACT_ATTACHED,
        EventType.PROPOSAL_ARTIFACT_ATTACHED,
        EventType.TOOL_INVOCATION_REQUESTED,
        EventType.TOOL_INVOCATION_RUNNING,
        EventType.TOOL_INVOCATION_COMPLETED,
        EventType.TOOL_INVOCATION_FAILED,
        EventType.TOOL_EXECUTION_STARTED,
        EventType.TOOL_EXECUTION_COMPLETED,
        EventType.TOOL_EXECUTION_FAILED,
        EventType.PROPOSAL_GENERATED,
        EventType.PROPOSAL_RESOLVED,
        EventType.DECISION_RECORD_CREATED,
    }
)


class ArtifactLineageProjectionBuilder(
    BaseProjectionBuilder[str, ArtifactLineageProjection]
):
    projection_type = ARTIFACT_LINEAGE_PROJECTION_TYPE
    schema_info = ProjectionSchemaInfo(
        projection_type=projection_type,
        schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
        builder_name="ArtifactLineageProjectionBuilder",
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

    def build(self, source: str) -> ArtifactLineageProjection:
        try:
            projection = self.build_read_only()
        except Exception as exc:
            self._events.emit_event_sync(
                event_type=EventType.ARTIFACT_LINEAGE_RECONSTRUCTION_FAILED,
                severity=Severity.ERROR,
                message=f"Artifact lineage reconstruction failed: {exc}",
                metadata={
                    "projection_name": self.projection_type,
                    "projection_version": self.schema_info.schema_version,
                    "source": source,
                    "error_type": type(exc).__name__,
                },
            )
            raise

        self._events.emit_event_sync(
            event_type=EventType.ARTIFACT_LINEAGE_UPDATED,
            message="Artifact lineage projection updated",
            metadata={
                "projection_name": self.projection_type,
                "projection_version": self.schema_info.schema_version,
                "record_count": len(projection.records),
                "orphan_count": projection.summary.orphaned_artifacts,
            },
        )
        if (
            projection.summary.orphaned_artifacts
            or projection.incomplete_event_ids
            or any(
                record.lineage_status == "incomplete"
                for record in projection.records
            )
        ):
            self._events.emit_event_sync(
                event_type=EventType.ARTIFACT_LINEAGE_INCOMPLETE,
                severity=Severity.WARNING,
                message="Artifact lineage reconstruction is incomplete",
                metadata={
                    "projection_name": self.projection_type,
                    "projection_version": self.schema_info.schema_version,
                    "orphan_count": projection.summary.orphaned_artifacts,
                    "incomplete_event_ids": projection.incomplete_event_ids,
                },
            )
        self._events.emit_event_sync(
            event_type=EventType.ARTIFACT_LINEAGE_REBUILT,
            message="Artifact lineage projection rebuilt",
            metadata={
                "projection_name": self.projection_type,
                "projection_version": self.schema_info.schema_version,
                "record_count": len(projection.records),
                "source": source,
            },
        )
        return projection

    def build_read_only(self) -> ArtifactLineageProjection:
        events = sorted(
            (
                event
                for event in self._events.list_persisted_events()
                if event.type in ARTIFACT_LINEAGE_SOURCE_EVENT_TYPES
            ),
            key=lambda event: (event.id, event.ts, event.type.value),
        )
        records, incomplete_event_ids = self._records(events)
        return ArtifactLineageProjection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=self._clock(),
                source=ARTIFACT_LINEAGE_SOURCE,
            ),
            records=records,
            summary=self._summary(records),
            incomplete_event_ids=incomplete_event_ids,
        )

    def _records(
        self,
        events: list[RuntimeEvent],
    ) -> tuple[list[ArtifactLineageRecord], list[int]]:
        artifact_events: dict[str, list[RuntimeEvent]] = defaultdict(list)
        runtime_links: dict[str, list[RuntimeEvent]] = defaultdict(list)
        proposal_links: dict[str, list[RuntimeEvent]] = defaultdict(list)
        tool_links: dict[str, list[RuntimeEvent]] = defaultdict(list)
        proposal_events: dict[str, list[RuntimeEvent]] = defaultdict(list)
        proposal_by_recommendation: dict[str, set[str]] = defaultdict(set)
        decisions_by_proposal: dict[str, set[str]] = defaultdict(set)
        direct_decisions: dict[str, set[str]] = defaultdict(set)
        incomplete_event_ids: list[int] = []

        decision_events: list[RuntimeEvent] = []
        for event in events:
            metadata = event.metadata
            if event.type == EventType.ARTIFACT_CREATED:
                artifact_id = _string(metadata.get("artifact_id"))
                if artifact_id is None:
                    incomplete_event_ids.append(event.id)
                    continue
                artifact_events[artifact_id].append(event)
                decision_id = _string(metadata.get("decision_id"))
                if decision_id is not None:
                    direct_decisions[artifact_id].add(decision_id)
            elif event.type == EventType.RUNTIME_ARTIFACT_ATTACHED:
                artifact_id = _string(metadata.get("artifact_id"))
                if artifact_id is None:
                    incomplete_event_ids.append(event.id)
                    continue
                runtime_links[artifact_id].append(event)
            elif event.type == EventType.PROPOSAL_ARTIFACT_ATTACHED:
                artifact_id = _string(metadata.get("artifact_id"))
                proposal_id = _string(metadata.get("proposal_id"))
                if artifact_id is None or proposal_id is None:
                    incomplete_event_ids.append(event.id)
                    continue
                proposal_links[artifact_id].append(event)
            elif event.type in {
                EventType.TOOL_INVOCATION_COMPLETED,
                EventType.TOOL_EXECUTION_COMPLETED,
            }:
                invocation_id = _string(
                    metadata.get("tool_invocation_id")
                )
                for artifact_id in _output_artifact_ids(metadata):
                    if invocation_id is not None:
                        tool_links[artifact_id].append(event)
            elif event.type in {
                EventType.PROPOSAL_GENERATED,
                EventType.PROPOSAL_RESOLVED,
            }:
                proposal_id = _string(metadata.get("proposal_id"))
                if proposal_id is None:
                    incomplete_event_ids.append(event.id)
                    continue
                proposal_events[proposal_id].append(event)
                if metadata.get("source_type") == "planner_recommendation":
                    recommendation_id = _string(metadata.get("source_id"))
                    if recommendation_id is not None:
                        proposal_by_recommendation[
                            recommendation_id
                        ].add(proposal_id)
            elif event.type == EventType.DECISION_RECORD_CREATED:
                decision_id = _string(metadata.get("decision_id"))
                if decision_id is None:
                    incomplete_event_ids.append(event.id)
                    continue
                decision_events.append(event)

        for event in decision_events:
            metadata = event.metadata
            decision_id = str(metadata["decision_id"])
            proposal_ids = set(
                _string_list(metadata.get("related_proposal_ids"))
            )
            proposal_id = _string(metadata.get("proposal_id"))
            if proposal_id is not None:
                proposal_ids.add(proposal_id)
            if metadata.get("selected_entity_type") == "planner_recommendation":
                recommendation_id = _string(
                    metadata.get("selected_entity_id")
                )
                if recommendation_id is not None:
                    proposal_ids.update(
                        proposal_by_recommendation.get(
                            recommendation_id,
                            set(),
                        )
                    )
            for linked_proposal_id in proposal_ids:
                decisions_by_proposal[linked_proposal_id].add(decision_id)
            for artifact_id in _string_list(
                metadata.get("related_artifact_ids")
            ):
                direct_decisions[artifact_id].add(decision_id)
        known_decision_ids = {
            str(event.metadata["decision_id"]) for event in decision_events
        }

        all_artifact_ids = (
            set(artifact_events)
            | set(runtime_links)
            | set(proposal_links)
            | set(tool_links)
            | set(direct_decisions)
        )
        records: list[ArtifactLineageRecord] = []
        for artifact_id in sorted(all_artifact_ids):
            creations = artifact_events.get(artifact_id, [])
            references = (
                runtime_links.get(artifact_id, [])
                + proposal_links.get(artifact_id, [])
                + tool_links.get(artifact_id, [])
            )
            incomplete_reasons: list[str] = []
            if not creations:
                incomplete_reasons.append("missing_artifact_creation")
                anchor = min(references, key=lambda event: event.id)
                artifact_path = f"unknown:{artifact_id}"
                artifact_type = "unknown"
            else:
                anchor = creations[0]
                artifact_path = (
                    _string(creations[-1].metadata.get("path"))
                    or f"unknown:{artifact_id}"
                )
                artifact_type = (
                    _string(creations[-1].metadata.get("kind"))
                    or "unknown"
                )
                if artifact_path.startswith("unknown:"):
                    incomplete_reasons.append("missing_artifact_path")
                if artifact_type == "unknown" and (
                    creations[-1].metadata.get("kind") is not None
                ):
                    incomplete_reasons.append("invalid_artifact_type")

            proposal_ids = {
                proposal_id
                for event in proposal_links.get(artifact_id, [])
                if (
                    proposal_id := _string(
                        event.metadata.get("proposal_id")
                    )
                )
                is not None
            }
            proposal_ids.update(
                proposal_id
                for event in creations
                if (
                    proposal_id := _string(
                        event.metadata.get("proposal_id")
                    )
                )
                is not None
            )
            missing_proposals = sorted(
                proposal_id
                for proposal_id in proposal_ids
                if proposal_id not in proposal_events
            )
            if missing_proposals:
                incomplete_reasons.append("missing_proposal")

            decision_ids = set(direct_decisions.get(artifact_id, set()))
            for proposal_id in proposal_ids:
                decision_ids.update(
                    decisions_by_proposal.get(proposal_id, set())
                )
            if any(
                decision_id not in known_decision_ids
                for decision_id in decision_ids
            ):
                incomplete_reasons.append("missing_decision")
            session_ids = {
                session_id
                for event in runtime_links.get(artifact_id, [])
                if (
                    session_id := _string(
                        event.metadata.get("session_id")
                    )
                )
                is not None
            }
            session_ids.update(
                session_id
                for event in tool_links.get(artifact_id, [])
                if (
                    session_id := _string(
                        event.metadata.get("session_id")
                    )
                )
                is not None
            )
            invocation_ids = {
                invocation_id
                for event in tool_links.get(artifact_id, [])
                if (
                    invocation_id := _string(
                        event.metadata.get("tool_invocation_id")
                    )
                )
                is not None
            }
            tool_ids = {
                tool_id
                for event in tool_links.get(artifact_id, [])
                if (
                    tool_id := _string(event.metadata.get("tool_id"))
                )
                is not None
            }
            parent_artifact_ids = sorted(
                {
                    parent_id
                    for event in creations
                    for parent_id in _artifact_parent_ids(event.metadata)
                    if parent_id != artifact_id
                }
            )
            missing_parents = [
                parent_id
                for parent_id in parent_artifact_ids
                if parent_id not in all_artifact_ids
            ]
            if missing_parents:
                incomplete_reasons.append("missing_parent_artifact")

            linked = bool(
                session_ids
                or invocation_ids
                or proposal_ids
                or decision_ids
                or parent_artifact_ids
            )
            if incomplete_reasons:
                status = "incomplete"
            elif linked:
                status = "linked"
            else:
                status = "orphaned"
            related_events = sorted(
                {
                    event.id
                    for event in (
                        creations
                        + references
                        + [
                            event
                            for proposal_id in proposal_ids
                            for event in proposal_events.get(
                                proposal_id,
                                [],
                            )
                        ]
                        + [
                            event
                            for event in decision_events
                            if event.metadata.get("decision_id")
                            in decision_ids
                        ]
                    )
                }
            )
            created_at, created_incomplete = _datetime_value(
                anchor.metadata.get("created_at"),
                fallback=anchor.ts,
            )
            update_event = max(
                creations + references,
                key=lambda event: event.id,
            )
            update_timestamp = (
                update_event.metadata.get("updated_at")
                or update_event.metadata.get("completed_at")
            )
            if update_timestamp is None and update_event.id != anchor.id:
                update_timestamp = update_event.metadata.get("created_at")
            if update_timestamp is None:
                updated_at = created_at
                updated_incomplete = False
            else:
                updated_at, updated_incomplete = _datetime_value(
                    update_timestamp,
                    fallback=update_event.ts,
                )
            if created_incomplete:
                incomplete_reasons.append("invalid_created_at")
            if updated_incomplete:
                incomplete_reasons.append("invalid_updated_at")
            if incomplete_reasons:
                status = "incomplete"

            records.append(
                ArtifactLineageRecord(
                    artifact_id=artifact_id,
                    artifact_path=artifact_path,
                    artifact_type=artifact_type,
                    session_id=min(session_ids) if session_ids else None,
                    source_event_id=anchor.id,
                    producing_tool_invocation_id=(
                        min(invocation_ids) if invocation_ids else None
                    ),
                    proposal_id=min(proposal_ids) if proposal_ids else None,
                    decision_id=min(decision_ids) if decision_ids else None,
                    parent_artifact_ids=parent_artifact_ids,
                    related_event_ids=related_events,
                    created_at=created_at,
                    updated_at=updated_at,
                    lineage_status=status,
                    metadata={
                        "task_id": _first_string(
                            event.metadata.get("task_id")
                            for event in creations + references
                        ),
                        "orphaned": status == "orphaned",
                        "incomplete_reasons": sorted(
                            set(incomplete_reasons)
                        ),
                        "related_decision_ids": sorted(decision_ids),
                        "related_proposal_ids": sorted(proposal_ids),
                        "producing_tool_ids": sorted(tool_ids),
                    },
                )
            )
        records.sort(
            key=lambda record: (
                record.updated_at,
                record.source_event_id,
                record.artifact_id,
            )
        )
        return records, sorted(set(incomplete_event_ids))

    def _summary(
        self,
        records: list[ArtifactLineageRecord],
    ) -> ArtifactLineageSummary:
        artifact_types = Counter(
            record.artifact_type for record in records
        )
        producing_tools = Counter(
            tool_id
            for record in records
            for tool_id in record.metadata.get(
                "producing_tool_ids",
                [],
            )
            if isinstance(tool_id, str)
        )
        orphaned = sum(
            record.lineage_status == "orphaned" for record in records
        )
        decision_links = sum(
            record.decision_id is not None for record in records
        )
        proposal_links = sum(
            record.proposal_id is not None for record in records
        )
        tool_links = sum(
            record.producing_tool_invocation_id is not None
            for record in records
        )
        return ArtifactLineageSummary(
            total_artifacts=len(records),
            linked_artifacts=sum(
                (
                    record.session_id is not None
                    or record.producing_tool_invocation_id is not None
                    or record.proposal_id is not None
                    or record.decision_id is not None
                    or bool(record.parent_artifact_ids)
                )
                for record in records
            ),
            orphaned_artifacts=orphaned,
            artifact_types=dict(sorted(artifact_types.items())),
            producing_tools=dict(sorted(producing_tools.items())),
            decision_linked_artifacts=decision_links,
            proposal_linked_artifacts=proposal_links,
            last_lineage_update=max(
                (record.updated_at for record in records),
                default=None,
            ),
            artifact_lineage_records_total=len(records),
            artifact_lineage_orphans_total=orphaned,
            artifact_lineage_rebuilds_total=len(
                self._events.list_persisted_events(
                    event_type=EventType.ARTIFACT_LINEAGE_REBUILT.value
                )
            ),
            artifact_decision_links_total=decision_links,
            artifact_proposal_links_total=proposal_links,
            artifact_tool_links_total=tool_links,
        )


def _output_artifact_ids(metadata: dict[str, Any]) -> list[str]:
    output_payload = metadata.get("output_payload")
    if not isinstance(output_payload, dict):
        return []
    return _string_list(output_payload.get("artifacts"))


def _artifact_parent_ids(metadata: dict[str, Any]) -> list[str]:
    parents = _string_list(metadata.get("parent_artifact_ids"))
    artifact_metadata = metadata.get("metadata")
    if isinstance(artifact_metadata, dict):
        parents.extend(
            _string_list(artifact_metadata.get("parent_artifact_ids"))
        )
    return sorted(set(parents))


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


def _first_string(values: Any) -> str | None:
    return next(
        (value for value in values if isinstance(value, str) and value),
        None,
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


artifact_lineage_projection_builder = ArtifactLineageProjectionBuilder()
