from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from app.models.query_execution_record import QueryReconstructionInfo
from app.models.query_snapshot_export import (
    QuerySnapshotExport,
    QuerySnapshotExportDiagnostic,
    QuerySnapshotVerificationStatus,
)
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
from app.services.query_snapshot_manifest_service import (
    QuerySnapshotManifestService,
    query_snapshot_manifest_service,
)


class QuerySnapshotExportError(RuntimeError):
    def __init__(
        self,
        message: str,
        diagnostics: list[QuerySnapshotExportDiagnostic],
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


class QuerySnapshotExportService:
    def __init__(
        self,
        history: QueryHistoryService | None = None,
        lineage: QueryLineageService | None = None,
        manifests: QuerySnapshotManifestService | None = None,
        events: EventService | None = None,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
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
        self._manifests = manifests or (
            query_snapshot_manifest_service
            if self._events is event_service
            else QuerySnapshotManifestService(
                history=self._history,
                lineage=self._lineage,
                events=self._events,
            )
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    def export(self, execution_id: str) -> QuerySnapshotExport:
        export_id = self._id_factory()
        try:
            record, raw_reconstruction = (
                self._history.load_execution_snapshot(execution_id)
            )
        except QueryExecutionRecordNotFoundError:
            diagnostic = self._diagnostic(
                EventType.QUERY_SNAPSHOT_EXPORT_FAILED,
                execution_id=execution_id,
                query_name=None,
                query_version=None,
                export_id=export_id,
                message=(
                    f"Query execution record not found: {execution_id}"
                ),
            )
            self._emit(diagnostic, severity=Severity.ERROR)
            raise

        diagnostics = [
            self._diagnostic(
                EventType.QUERY_SNAPSHOT_EXPORT_STARTED,
                execution_id=record.execution_id,
                query_name=record.query_name,
                query_version=record.query_version,
                export_id=export_id,
            )
        ]
        self._emit(diagnostics[-1])
        content_hash: str | None = None

        try:
            reconstruction = QueryReconstructionInfo.model_validate(
                raw_reconstruction
            )
            lineage = self._lineage.generate(record.execution_id)
            manifest = self._manifests.generate(
                record.execution_id,
                generated_at=record.executed_at,
            )
            content_hash = manifest.content_hash
            verification_status = self._latest_verification_status(
                record.execution_id
            )
            exported_at = self._clock()
        except Exception as exc:
            message = f"Query snapshot export failed: {exc}"
            diagnostics.append(
                self._diagnostic(
                    EventType.QUERY_SNAPSHOT_EXPORT_FAILED,
                    execution_id=record.execution_id,
                    query_name=record.query_name,
                    query_version=record.query_version,
                    export_id=export_id,
                    content_hash=content_hash,
                    message=message,
                )
            )
            self._emit(diagnostics[-1], severity=Severity.ERROR)
            raise QuerySnapshotExportError(
                message,
                diagnostics,
            ) from exc

        diagnostics.append(
            self._diagnostic(
                EventType.QUERY_SNAPSHOT_EXPORT_COMPLETED,
                execution_id=record.execution_id,
                query_name=record.query_name,
                query_version=record.query_version,
                export_id=export_id,
                content_hash=content_hash,
            )
        )
        self._emit(diagnostics[-1])
        return QuerySnapshotExport(
            export_id=export_id,
            execution_id=record.execution_id,
            exported_at=exported_at,
            query_execution_record=record,
            reconstruction_info=reconstruction,
            lineage=lineage,
            manifest=manifest,
            verification_status=verification_status,
            diagnostics=diagnostics,
        )

    def _latest_verification_status(
        self,
        execution_id: str,
    ) -> QuerySnapshotVerificationStatus | None:
        events = [
            event
            for event in self._events.list_persisted_events(
                event_type=EventType.QUERY_VERIFICATION_COMPLETED.value
            )
            if event.metadata.get("execution_id") == execution_id
        ]
        if not events:
            return None
        metadata = events[-1].metadata
        verified = metadata.get("verified") is True
        difference_count = metadata.get("difference_count")
        if not isinstance(difference_count, int) or difference_count < 0:
            return None
        return QuerySnapshotVerificationStatus(
            status="verified" if verified else "drifted",
            verified=verified,
            difference_count=difference_count,
        )

    @staticmethod
    def _diagnostic(
        event_type: EventType,
        *,
        execution_id: str,
        query_name: str | None,
        query_version: int | None,
        export_id: str,
        content_hash: str | None = None,
        message: str | None = None,
    ) -> QuerySnapshotExportDiagnostic:
        return QuerySnapshotExportDiagnostic(
            event_type=event_type.value,
            execution_id=execution_id,
            query_name=query_name,
            query_version=query_version,
            export_id=export_id,
            content_hash=content_hash,
            message=message,
        )

    def _emit(
        self,
        diagnostic: QuerySnapshotExportDiagnostic,
        severity: Severity = Severity.INFO,
    ) -> None:
        self._events.emit_event_sync(
            event_type=diagnostic.event_type,
            severity=severity,
            message=(
                diagnostic.message
                or diagnostic.event_type.replace("_", " ").capitalize()
            ),
            metadata=diagnostic.model_dump(
                mode="json",
                exclude={"event_type", "message"},
            ),
        )


query_snapshot_export_service = QuerySnapshotExportService()
