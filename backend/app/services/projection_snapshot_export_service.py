from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from app.models.projection import (
    ProjectionSchemaInfo,
    ProjectionSnapshotExport,
    ProjectionSnapshotExportDiagnostic,
)
from app.models.runtime_event import EventType, Severity
from app.runtime.projection_registry import (
    ProjectionRegistry,
    projection_registry,
)
from app.services.event_service import EventService, event_service
from app.services.projection_lineage_service import (
    ProjectionLineageService,
)
from app.services.projection_rebuild_service import (
    ProjectionRebuildService,
)
from app.services.projection_snapshot_manifest_service import (
    normalize_projection_content,
)
from app.services.projection_verification_service import (
    ProjectionVerificationService,
)
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)


class ProjectionSnapshotExportError(RuntimeError):
    def __init__(
        self,
        message: str,
        diagnostics: list[ProjectionSnapshotExportDiagnostic],
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


class ProjectionSnapshotExportService:
    def __init__(
        self,
        registry: ProjectionRegistry | None = None,
        rebuilds: ProjectionRebuildService | None = None,
        verification: ProjectionVerificationService | None = None,
        lineage: ProjectionLineageService | None = None,
        events: EventService | None = None,
        sessions: RuntimeSessionService | None = None,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._registry = registry or projection_registry
        self._events = events or event_service
        self._sessions = sessions or runtime_session_service
        self._rebuilds = rebuilds or ProjectionRebuildService(
            registry=self._registry,
            events=self._events,
        )
        self._verification = verification or ProjectionVerificationService(
            registry=self._registry,
            rebuilds=self._rebuilds,
            events=self._events,
        )
        self._lineage = lineage or ProjectionLineageService(
            registry=self._registry,
            events=self._events,
            sessions=self._sessions,
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    def export(
        self,
        projection_name: str,
        source: str,
        verify: bool = False,
        include_lineage: bool = True,
    ) -> ProjectionSnapshotExport:
        schema = self._registry.get_schema(projection_name)
        export_id = self._id_factory()
        diagnostics = [
            self._diagnostic(
                EventType.PROJECTION_SNAPSHOT_EXPORT_STARTED,
                schema,
                export_id,
            )
        ]
        self._emit(diagnostics[-1])

        content_hash: str | None = None
        try:
            rebuilt = self._rebuilds.rebuild(projection_name, source)
            content_hash = rebuilt.snapshot_manifest.content_hash
            verification_status = None
            if verify:
                verification = self._verification.verify(
                    projection_name,
                    source,
                )
                verification_status = (
                    "verified" if verification.verified else "drifted"
                )

            exported_at = self._clock()
            snapshot_manifest = rebuilt.snapshot_manifest.model_copy(
                update={
                    "generated_at": self._source_timestamp(
                        source,
                        rebuilt.snapshot_manifest.generated_at,
                    ),
                    "verification_status": verification_status,
                }
            )
            projection = normalize_projection_content(
                rebuilt.projection_data,
            )
            lineage = (
                self._lineage.generate(projection_name, source)
                if include_lineage
                else None
            )
        except Exception as exc:
            message = f"Projection snapshot export failed: {exc}"
            diagnostics.append(
                self._diagnostic(
                    EventType.PROJECTION_SNAPSHOT_EXPORT_FAILED,
                    schema,
                    export_id,
                    content_hash=content_hash,
                    message=message,
                )
            )
            self._emit(diagnostics[-1], severity=Severity.ERROR)
            raise ProjectionSnapshotExportError(
                message,
                diagnostics,
            ) from exc

        diagnostics.append(
            self._diagnostic(
                EventType.PROJECTION_SNAPSHOT_EXPORT_COMPLETED,
                schema,
                export_id,
                content_hash=content_hash,
            )
        )
        self._emit(diagnostics[-1])
        return ProjectionSnapshotExport(
            export_id=export_id,
            projection_name=projection_name,
            exported_at=exported_at,
            projection=projection,
            snapshot_manifest=snapshot_manifest,
            reconstruction_info=rebuilt.reconstruction,
            verification_status=verification_status,
            lineage=lineage,
            diagnostics=diagnostics,
        )

    def _source_timestamp(
        self,
        source: str,
        fallback: datetime,
    ) -> datetime:
        try:
            return self._sessions.get_session(source).created_at
        except Exception:
            return fallback

    def _diagnostic(
        self,
        event_type: EventType,
        schema: ProjectionSchemaInfo,
        export_id: str,
        content_hash: str | None = None,
        message: str | None = None,
    ) -> ProjectionSnapshotExportDiagnostic:
        return ProjectionSnapshotExportDiagnostic(
            event_type=event_type.value,
            projection_name=schema.projection_type,
            export_id=export_id,
            schema_version=schema.schema_version,
            builder_name=schema.builder_name,
            content_hash=content_hash,
            message=message,
        )

    def _emit(
        self,
        diagnostic: ProjectionSnapshotExportDiagnostic,
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


projection_snapshot_export_service = ProjectionSnapshotExportService()
