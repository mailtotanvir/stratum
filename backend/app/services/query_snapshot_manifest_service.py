import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from app.models.query_snapshot_manifest import QuerySnapshotManifest
from app.models.runtime_event import EventType, Severity
from app.services.event_service import EventService, event_service
from app.services.query_history_service import (
    QueryExecutionRecordNotFoundError,
    QueryHistoryService,
    query_history_service,
)
from app.services.query_lineage_service import (
    QueryLineageService,
    query_lineage_service,
)


VOLATILE_HASH_FIELDS = frozenset(
    {
        "built_at",
        "executed_at",
        "execution_timestamp",
        "generated_at",
        "requested_at",
        "verified_at",
    }
)
USE_RECORDED_RESULT = object()


class QueryManifestGenerationError(RuntimeError):
    pass


class QuerySnapshotManifestService:
    def __init__(
        self,
        history: QueryHistoryService | None = None,
        lineage: QueryLineageService | None = None,
        events: EventService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._events = events or event_service
        self._history = history or (
            query_history_service
            if self._events is event_service
            else QueryHistoryService(self._events)
        )
        self._lineage = lineage or (
            query_lineage_service
            if self._events is event_service
            else QueryLineageService(
                history=self._history,
                events=self._events,
            )
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    def generate(
        self,
        execution_id: str,
        *,
        result_summary: Any = USE_RECORDED_RESULT,
        generated_at: datetime | None = None,
    ) -> QuerySnapshotManifest:
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
            lineage = self._lineage.generate(execution_id)
            parameter_hash = stable_query_hash(
                lineage.reconstruction_info.parameter_snapshot
            )
            result_hash = stable_query_hash(
                record.result_summary
                if result_summary is USE_RECORDED_RESULT
                else result_summary
            )
            content_hash = stable_query_hash(
                {
                    "execution_id": record.execution_id,
                    "query_name": record.query_name,
                    "query_version": record.query_version,
                    "handler_name": lineage.handler_name,
                    "parameter_hash": parameter_hash,
                    "result_hash": result_hash,
                    "lineage_reference": {
                        "execution_id": lineage.execution_id,
                        "lineage_version": lineage.lineage_version,
                    },
                    "reconstruction_reference": {
                        "query_name": raw_reconstruction.get("query_name"),
                        "query_version": raw_reconstruction.get(
                            "query_version"
                        ),
                        "reconstruction_version": (
                            lineage.reconstruction_info.reconstruction_version
                        ),
                    },
                }
            )
            manifest = QuerySnapshotManifest(
                execution_id=record.execution_id,
                query_name=record.query_name,
                query_version=record.query_version,
                handler_name=lineage.handler_name,
                generated_at=generated_at or self._clock(),
                parameter_hash=parameter_hash,
                result_hash=result_hash,
                lineage_version=lineage.lineage_version,
                reconstruction_version=(
                    lineage.reconstruction_info.reconstruction_version
                ),
                content_hash=content_hash,
            )
        except Exception as exc:
            self._emit_failure(
                execution_id=record.execution_id,
                query_name=record.query_name,
                query_version=record.query_version,
            )
            raise QueryManifestGenerationError(
                f"Query manifest generation failed: {exc}"
            ) from exc

        metadata = {
            "execution_id": record.execution_id,
            "query_name": record.query_name,
            "query_version": record.query_version,
            "content_hash": content_hash,
        }
        self._events.emit_event_sync(
            event_type=EventType.QUERY_MANIFEST_HASH_COMPUTED,
            message=f"Query manifest hash computed: {record.query_name}",
            metadata=metadata,
        )
        self._events.emit_event_sync(
            event_type=EventType.QUERY_MANIFEST_GENERATED,
            message=f"Query manifest generated: {record.query_name}",
            metadata=metadata,
        )
        return manifest

    def _emit_failure(
        self,
        *,
        execution_id: str,
        query_name: str | None,
        query_version: int | None,
    ) -> None:
        self._events.emit_event_sync(
            event_type=EventType.QUERY_MANIFEST_GENERATION_FAILED,
            severity=Severity.ERROR,
            message="Query manifest generation failed",
            metadata={
                "execution_id": execution_id,
                "query_name": query_name,
                "query_version": query_version,
                "content_hash": None,
            },
        )


def stable_query_hash(
    content: Any,
    *,
    include_volatile: bool = False,
) -> str:
    normalized = normalize_query_content(
        content,
        include_volatile=include_volatile,
    )
    serialized = json.dumps(
        normalized,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def normalize_query_content(
    value: Any,
    *,
    include_volatile: bool = False,
) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {
            key: normalize_query_content(
                item,
                include_volatile=include_volatile,
            )
            for key, item in sorted(value.items())
            if include_volatile or key not in VOLATILE_HASH_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [
            normalize_query_content(
                item,
                include_volatile=include_volatile,
            )
            for item in value
        ]
    return value


query_snapshot_manifest_service = QuerySnapshotManifestService()
