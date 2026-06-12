from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from app.models.projection import (
    ProjectionDifference,
    ProjectionSchemaInfo,
    ProjectionVerificationDiagnostic,
    ProjectionVerificationResult,
)
from app.models.runtime_event import EventType, Severity
from app.runtime.projection_registry import (
    ProjectionRegistry,
    projection_registry,
)
from app.services.event_service import EventService, event_service
from app.services.projection_rebuild_service import (
    ProjectionRebuildService,
    projection_rebuild_service,
)
from app.services.projection_snapshot_manifest_service import (
    ProjectionSnapshotManifestService,
)


class ProjectionVerificationError(RuntimeError):
    def __init__(
        self,
        message: str,
        diagnostics: list[ProjectionVerificationDiagnostic],
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


class ProjectionVerificationService:
    def __init__(
        self,
        registry: ProjectionRegistry | None = None,
        rebuilds: ProjectionRebuildService | None = None,
        events: EventService | None = None,
        manifests: ProjectionSnapshotManifestService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._registry = registry or projection_registry
        self._rebuilds = rebuilds or projection_rebuild_service
        self._events = events or event_service
        self._manifests = manifests or ProjectionSnapshotManifestService(
            registry=self._registry,
            events=self._events,
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    def verify(
        self,
        projection_name: str,
        source: str,
    ) -> ProjectionVerificationResult:
        builder = self._registry.get(projection_name)
        schema = self._registry.get_schema(projection_name)
        diagnostics = [
            self._diagnostic(
                EventType.PROJECTION_VERIFICATION_STARTED,
                schema,
                difference_count=0,
            )
        ]
        self._emit(diagnostics[-1])

        try:
            current_projection = builder.build(source)
            rebuilt = self._rebuilds.rebuild(projection_name, source)
            differences = compare_projection_values(
                rebuilt.projection_data,
                current_projection,
            )
            verified = not differences
            verification_status = "verified" if verified else "drifted"
            current_manifest = self._manifests.generate(
                schema,
                current_projection,
                source,
                verification_status=verification_status,
            )
            rebuilt_manifest = rebuilt.snapshot_manifest.model_copy(
                update={"verification_status": verification_status}
            )
            hash_match = (
                current_manifest.content_hash
                == rebuilt_manifest.content_hash
            )
        except Exception as exc:
            message = f"Projection verification failed: {exc}"
            diagnostics.append(
                self._diagnostic(
                    EventType.PROJECTION_VERIFICATION_FAILED,
                    schema,
                    difference_count=0,
                    message=message,
                )
            )
            self._emit(diagnostics[-1], severity=Severity.ERROR)
            raise ProjectionVerificationError(
                message,
                diagnostics,
            ) from exc

        diagnostics.append(
            self._diagnostic(
                EventType.PROJECTION_VERIFICATION_COMPLETED,
                schema,
                difference_count=len(differences),
            )
        )
        self._emit(diagnostics[-1])
        return ProjectionVerificationResult(
            projection_name=projection_name,
            verified=verified,
            verified_at=self._clock(),
            schema_version=schema.schema_version,
            builder_name=schema.builder_name,
            differences=differences,
            reconstruction_info=rebuilt.reconstruction,
            current_manifest=current_manifest,
            rebuilt_manifest=rebuilt_manifest,
            hash_match=hash_match,
            diagnostics=diagnostics,
        )

    def _diagnostic(
        self,
        event_type: EventType,
        schema: ProjectionSchemaInfo,
        difference_count: int,
        message: str | None = None,
    ) -> ProjectionVerificationDiagnostic:
        return ProjectionVerificationDiagnostic(
            event_type=event_type.value,
            projection_name=schema.projection_type,
            schema_version=schema.schema_version,
            builder_name=schema.builder_name,
            difference_count=difference_count,
            message=message,
        )

    def _emit(
        self,
        diagnostic: ProjectionVerificationDiagnostic,
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


def compare_projection_values(
    expected: Any,
    actual: Any,
) -> list[ProjectionDifference]:
    differences: list[ProjectionDifference] = []
    _compare_values(
        _normalize_projection_value(expected),
        _normalize_projection_value(actual),
        "$",
        differences,
    )
    return differences


def _normalize_projection_value(
    value: Any,
    in_metadata: bool = False,
) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {
            key: _normalize_projection_value(
                item,
                in_metadata=in_metadata or key == "metadata",
            )
            for key, item in value.items()
            if not (in_metadata and key == "built_at")
        }
    if isinstance(value, (list, tuple)):
        return [
            _normalize_projection_value(item, in_metadata=in_metadata)
            for item in value
        ]
    return value


def _compare_values(
    expected: Any,
    actual: Any,
    field_path: str,
    differences: list[ProjectionDifference],
) -> None:
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(expected.keys() | actual.keys()):
            child_path = f"{field_path}.{key}"
            if key not in actual:
                differences.append(
                    _difference(
                        child_path,
                        expected[key],
                        None,
                        "missing_field",
                    )
                )
            elif key not in expected:
                differences.append(
                    _difference(
                        child_path,
                        None,
                        actual[key],
                        "unexpected_field",
                    )
                )
            else:
                _compare_values(
                    expected[key],
                    actual[key],
                    child_path,
                    differences,
                )
        return

    if isinstance(expected, list) and isinstance(actual, list):
        shared_length = min(len(expected), len(actual))
        for index in range(shared_length):
            _compare_values(
                expected[index],
                actual[index],
                f"{field_path}[{index}]",
                differences,
            )
        for index in range(shared_length, len(expected)):
            differences.append(
                _difference(
                    f"{field_path}[{index}]",
                    expected[index],
                    None,
                    "missing_field",
                )
            )
        for index in range(shared_length, len(actual)):
            differences.append(
                _difference(
                    f"{field_path}[{index}]",
                    None,
                    actual[index],
                    "unexpected_field",
                )
            )
        return

    if expected != actual:
        differences.append(
            _difference(
                field_path,
                expected,
                actual,
                "value_mismatch",
            )
        )


def _difference(
    field_path: str,
    expected_value: Any,
    actual_value: Any,
    difference_type: str,
) -> ProjectionDifference:
    if ".metadata" in field_path:
        difference_type = "metadata_mismatch"
    return ProjectionDifference(
        field_path=field_path,
        expected_value=expected_value,
        actual_value=actual_value,
        difference_type=difference_type,
    )


projection_verification_service = ProjectionVerificationService()
