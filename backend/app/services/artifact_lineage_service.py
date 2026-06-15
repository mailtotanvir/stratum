from app.models.artifact_lineage import (
    ArtifactLineageChain,
    ArtifactLineageEvents,
    ArtifactLineageEventSummary,
    ArtifactLineageRecord,
    ArtifactLineageSummary,
)
from app.services.artifact_lineage_projection_builder_service import (
    ArtifactLineageProjectionBuilder,
    artifact_lineage_projection_builder,
)
from app.services.event_service import EventService, event_service


class ArtifactLineageNotFoundError(LookupError):
    pass


class ArtifactLineageService:
    def __init__(
        self,
        builder: ArtifactLineageProjectionBuilder | None = None,
        events: EventService | None = None,
    ) -> None:
        self._builder = builder or artifact_lineage_projection_builder
        self._events = events or event_service

    def list_records(self) -> list[ArtifactLineageRecord]:
        return list(reversed(self._builder.build_read_only().records))

    def get_chain(self, artifact_id: str) -> ArtifactLineageChain:
        records = {
            record.artifact_id: record for record in self.list_records()
        }
        target = records.get(artifact_id)
        if target is None:
            raise ArtifactLineageNotFoundError(
                f"Artifact lineage not found: {artifact_id}"
            )
        ordered: list[ArtifactLineageRecord] = []
        visited: set[str] = set()
        complete = target.lineage_status != "incomplete"

        def add(record: ArtifactLineageRecord) -> None:
            nonlocal complete
            if record.artifact_id in visited:
                complete = False
                return
            visited.add(record.artifact_id)
            for parent_id in record.parent_artifact_ids:
                parent = records.get(parent_id)
                if parent is None:
                    complete = False
                    continue
                add(parent)
            ordered.append(record)
            complete = (
                complete and record.lineage_status != "incomplete"
            )

        add(target)
        return ArtifactLineageChain(
            artifact_id=artifact_id,
            records=ordered,
            complete=complete,
        )

    def related_events(self, artifact_id: str) -> ArtifactLineageEvents:
        chain = self.get_chain(artifact_id)
        record = next(
            item
            for item in chain.records
            if item.artifact_id == artifact_id
        )
        related_ids = set(record.related_event_ids)
        events = [
            ArtifactLineageEventSummary(
                event_id=event.id,
                event_type=event.type.value,
                occurred_at=event.ts,
                severity=event.severity.value,
                message=event.message,
            )
            for event in self._events.list_persisted_events()
            if event.id in related_ids
        ]
        events.sort(
            key=lambda event: (
                event.occurred_at,
                event.event_id,
                event.event_type,
            )
        )
        return ArtifactLineageEvents(
            artifact_id=artifact_id,
            events=events,
            event_count=len(events),
        )

    def summary(self) -> ArtifactLineageSummary:
        return self._builder.build_read_only().summary


artifact_lineage_service = ArtifactLineageService()
