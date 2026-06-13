from collections import Counter, defaultdict
from typing import Any

from pydantic import ValidationError

from app.models.query_execution_record import QueryReconstructionInfo
from app.models.query_lineage import QueryLineage
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.models.runtime_query import RuntimeQuery
from app.query.runtime_query_registry import (
    RuntimeQueryRegistry,
    runtime_query_registry,
)
from app.services.event_service import EventService, event_service
from app.services.query_history_service import (
    QueryExecutionRecordNotFoundError,
    QueryHistoryService,
    query_history_service,
)


LINEAGE_VERSION = 1
EVENT_ACTION_SUFFIXES = (
    "_attached",
    "_blocked",
    "_completed",
    "_created",
    "_disabled",
    "_dismissed",
    "_enabled",
    "_failed",
    "_generated",
    "_ignored",
    "_interrupted",
    "_promoted",
    "_recorded",
    "_requested",
    "_resolved",
    "_responded",
    "_retrieved",
    "_running",
    "_started",
    "_stopped",
)


class QueryLineageGenerationError(RuntimeError):
    pass


class QueryLineageService:
    def __init__(
        self,
        registry: RuntimeQueryRegistry | None = None,
        history: QueryHistoryService | None = None,
        events: EventService | None = None,
    ) -> None:
        self._registry = registry or runtime_query_registry
        self._events = events or event_service
        self._history = history or (
            query_history_service
            if self._events is event_service
            else QueryHistoryService(self._events)
        )

    def generate(self, execution_id: str) -> QueryLineage:
        try:
            record, raw_reconstruction = (
                self._history.load_execution_snapshot(execution_id)
            )
        except QueryExecutionRecordNotFoundError:
            self._emit_failure(
                execution_id=execution_id,
                query_name=None,
                query_version=None,
            )
            raise

        try:
            reconstruction = QueryReconstructionInfo.model_validate(
                raw_reconstruction
            )
            handler = self._registry.get(record.query_name)
            metadata = self._registry.get_metadata_snapshot(
                record.query_name
            )
            if metadata.query_version != record.query_version:
                raise ValueError(
                    "Runtime query version does not match history record"
                )
            if type(handler).__name__ != reconstruction.handler_name:
                raise ValueError(
                    "Runtime query handler does not match reconstruction"
                )
            source_events = self._source_events(
                reconstruction.parameter_snapshot
            )
            source_types, source_counts = self._source_description(
                metadata,
                source_events,
            )
            source_identifiers = self._source_identifiers(
                reconstruction.parameter_snapshot,
                source_events,
            )
            lineage = QueryLineage(
                execution_id=record.execution_id,
                query_name=record.query_name,
                query_version=record.query_version,
                handler_name=type(handler).__name__,
                generated_at=record.executed_at,
                source_types=source_types,
                source_identifiers=source_identifiers,
                source_counts=source_counts,
                reconstruction_info=reconstruction,
                lineage_version=LINEAGE_VERSION,
            )
        except Exception as exc:
            self._emit_failure(
                execution_id=record.execution_id,
                query_name=record.query_name,
                query_version=record.query_version,
            )
            if isinstance(exc, ValidationError):
                detail = "incomplete reconstruction metadata"
            else:
                detail = str(exc)
            raise QueryLineageGenerationError(
                f"Query lineage generation failed: {detail}"
            ) from exc

        self._events.emit_event_sync(
            event_type=EventType.QUERY_LINEAGE_GENERATED,
            message=f"Query lineage generated: {record.query_name}",
            metadata={
                "execution_id": record.execution_id,
                "query_name": record.query_name,
                "query_version": record.query_version,
                "source_count": 1 + len(source_events),
            },
        )
        return lineage

    def _source_events(
        self,
        parameters: dict[str, Any],
    ) -> list[RuntimeEvent]:
        identifiers = {
            value
            for key, value in parameters.items()
            if key.endswith("_id") and isinstance(value, (str, int))
        }
        if not identifiers:
            return []
        return [
            event
            for event in self._events.list_persisted_events()
            if any(
                key.endswith("_id") and value in identifiers
                for key, value in event.metadata.items()
            )
            and not event.type.value.startswith("query_")
            and not event.type.value.startswith("runtime_query_")
        ]

    def _source_description(
        self,
        metadata: RuntimeQuery,
        source_events: list[RuntimeEvent],
    ) -> tuple[list[str], dict[str, int]]:
        primary_source = _query_source_type(metadata.query_type)
        counts: Counter[str] = Counter({primary_source: 1})
        if source_events:
            counts["runtime_event"] = len(source_events)
        for event in source_events:
            counts[_event_source_type(event.type.value)] += 1
        return sorted(counts), dict(sorted(counts.items()))

    def _source_identifiers(
        self,
        parameters: dict[str, Any],
        source_events: list[RuntimeEvent],
    ) -> dict[str, Any]:
        identifiers: dict[str, Any] = {}
        discovered: defaultdict[str, set[str | int]] = defaultdict(set)
        for key, value in parameters.items():
            if key.endswith("_id") and isinstance(value, (str, int)):
                identifiers[key] = value
        for event in source_events:
            for key, value in event.metadata.items():
                if not key.endswith("_id") or not isinstance(
                    value,
                    (str, int),
                ):
                    continue
                if key in identifiers and identifiers[key] == value:
                    continue
                discovered[f"{key[:-3]}_ids"].add(value)
        if source_events:
            identifiers["event_ids"] = [
                event.id for event in source_events
            ]
        for key in sorted(discovered):
            identifiers[key] = sorted(
                discovered[key],
                key=lambda value: str(value),
            )
        return dict(sorted(identifiers.items()))

    def _emit_failure(
        self,
        *,
        execution_id: str,
        query_name: str | None,
        query_version: int | None,
    ) -> None:
        self._events.emit_event_sync(
            event_type=EventType.QUERY_LINEAGE_GENERATION_FAILED,
            severity=Severity.ERROR,
            message="Query lineage generation failed",
            metadata={
                "execution_id": execution_id,
                "query_name": query_name,
                "query_version": query_version,
                "source_count": 0,
            },
        )


def _query_source_type(query_type: str) -> str:
    return {
        "session_query": "runtime_session",
        "decision_query": "decision_record",
        "projection_query": "projection",
        "diagnostic_query": "runtime_event",
    }.get(query_type, query_type.removesuffix("_query"))


def _event_source_type(event_type: str) -> str:
    for suffix in EVENT_ACTION_SUFFIXES:
        if event_type.endswith(suffix):
            return event_type[: -len(suffix)]
    return event_type


query_lineage_service = QueryLineageService()
