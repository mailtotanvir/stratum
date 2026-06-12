from app.models.projection import (
    ProjectionRebuildDiagnostic,
    ProjectionRebuildResult,
    ProjectionSchemaInfo,
)
from app.models.runtime_event import EventType, Severity
from app.runtime.projection_contract_validator import (
    ProjectionContractError,
    validate_projection_contract,
    validate_projection_result,
)
from app.runtime.projection_registry import (
    ProjectionRegistry,
    projection_registry,
)
from app.services.event_service import EventService, event_service
from app.services.projection_snapshot_manifest_service import (
    ProjectionSnapshotManifestService,
)


class ProjectionRebuildError(RuntimeError):
    def __init__(
        self,
        message: str,
        diagnostics: list[ProjectionRebuildDiagnostic],
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


class ProjectionRebuildValidationError(ProjectionRebuildError):
    pass


class ProjectionRebuildExecutionError(ProjectionRebuildError):
    pass


class ProjectionRebuildService:
    def __init__(
        self,
        registry: ProjectionRegistry | None = None,
        events: EventService | None = None,
        manifests: ProjectionSnapshotManifestService | None = None,
    ) -> None:
        self._registry = registry or projection_registry
        self._events = events or event_service
        self._manifests = manifests or ProjectionSnapshotManifestService(
            registry=self._registry,
            events=self._events,
        )

    def rebuild(
        self,
        projection_type: str,
        source: str,
    ) -> ProjectionRebuildResult:
        builder = self._registry.get(projection_type)
        schema = validate_projection_contract(builder)
        diagnostics = [
            self._diagnostic(
                EventType.PROJECTION_REBUILD_STARTED,
                schema,
                source,
            )
        ]
        self._emit(diagnostics[-1])

        try:
            projection_data = builder.build(source)
            validate_projection_result(projection_data, schema)
            snapshot_manifest = self._manifests.generate(
                schema,
                projection_data,
                source,
            )
        except ProjectionContractError as exc:
            diagnostics.append(
                self._diagnostic(
                    EventType.PROJECTION_REBUILD_FAILED,
                    schema,
                    source,
                    str(exc),
                )
            )
            self._emit(diagnostics[-1], severity=Severity.ERROR)
            raise ProjectionRebuildValidationError(
                str(exc),
                diagnostics,
            ) from exc
        except Exception as exc:
            message = f"Projection rebuild failed: {exc}"
            diagnostics.append(
                self._diagnostic(
                    EventType.PROJECTION_REBUILD_FAILED,
                    schema,
                    source,
                    message,
                )
            )
            self._emit(diagnostics[-1], severity=Severity.ERROR)
            raise ProjectionRebuildExecutionError(
                message,
                diagnostics,
            ) from exc

        diagnostics.append(
            self._diagnostic(
                EventType.PROJECTION_REBUILD_COMPLETED,
                schema,
                source,
            )
        )
        self._emit(diagnostics[-1])
        return ProjectionRebuildResult(
            projection_type=schema.projection_type,
            schema_version=schema.schema_version,
            builder_name=schema.builder_name,
            source=source,
            reconstruction=schema.reconstruction,
            projection_data=projection_data,
            snapshot_manifest=snapshot_manifest,
            diagnostics=diagnostics,
        )

    def _diagnostic(
        self,
        event_type: EventType,
        schema: ProjectionSchemaInfo,
        source: str,
        message: str | None = None,
    ) -> ProjectionRebuildDiagnostic:
        return ProjectionRebuildDiagnostic(
            event_type=event_type.value,
            projection_type=schema.projection_type,
            schema_version=schema.schema_version,
            builder_name=schema.builder_name,
            source=source,
            reconstruction=schema.reconstruction,
            message=message,
        )

    def _emit(
        self,
        diagnostic: ProjectionRebuildDiagnostic,
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


projection_rebuild_service = ProjectionRebuildService()
