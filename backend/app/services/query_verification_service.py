from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError

from app.models.query_execution_record import (
    QueryExecutionRecord,
    QueryReconstructionInfo,
)
from app.models.query_verification import (
    QueryDifference,
    QueryVerificationDiagnostic,
    QueryVerificationResult,
)
from app.models.runtime_event import EventType, Severity
from app.models.runtime_query_execution import RuntimeQueryExecutionRequest
from app.query.runtime_query_registry import (
    RuntimeQueryNotFoundError,
    RuntimeQueryRegistry,
    runtime_query_registry,
)
from app.services.event_service import EventService, event_service
from app.services.query_history_service import (
    QueryExecutionRecordNotFoundError,
    QueryHistoryService,
    query_history_service,
)
from app.services.query_lineage_service import (
    QueryLineageGenerationError,
    QueryLineageService,
)
from app.services.query_snapshot_manifest_service import (
    QueryManifestGenerationError,
    QuerySnapshotManifestService,
)
from app.services.runtime_query_execution_service import (
    validate_runtime_query_parameters,
)


class QueryVerificationError(RuntimeError):
    def __init__(
        self,
        message: str,
        diagnostics: list[QueryVerificationDiagnostic],
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


class QueryVersionMismatchError(QueryVerificationError):
    pass


class QueryReconstructionMetadataError(QueryVerificationError):
    pass


class QueryVerificationService:
    def __init__(
        self,
        registry: RuntimeQueryRegistry | None = None,
        history: QueryHistoryService | None = None,
        events: EventService | None = None,
        clock: Callable[[], datetime] | None = None,
        lineage: QueryLineageService | None = None,
        manifests: QuerySnapshotManifestService | None = None,
    ) -> None:
        self._registry = registry or runtime_query_registry
        self._events = events or event_service
        self._history = history or (
            query_history_service
            if self._events is event_service
            else QueryHistoryService(self._events)
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lineage = lineage or QueryLineageService(
            registry=self._registry,
            history=self._history,
            events=self._events,
        )
        self._manifests = manifests or QuerySnapshotManifestService(
            history=self._history,
            lineage=self._lineage,
            events=self._events,
            clock=self._clock,
        )

    def verify(self, execution_id: str) -> QueryVerificationResult:
        try:
            record, raw_reconstruction = (
                self._history.load_execution_snapshot(execution_id)
            )
        except QueryExecutionRecordNotFoundError:
            diagnostic = self._diagnostic(
                EventType.QUERY_VERIFICATION_FAILED,
                execution_id=execution_id,
                query_name=None,
                query_version=None,
                verified=False,
                difference_count=0,
                message=(
                    f"Query execution record not found: {execution_id}"
                ),
            )
            self._emit(diagnostic, severity=Severity.ERROR)
            raise

        diagnostics = [
            self._diagnostic(
                EventType.QUERY_VERIFICATION_STARTED,
                execution_id=record.execution_id,
                query_name=record.query_name,
                query_version=record.query_version,
                verified=False,
                difference_count=0,
            )
        ]
        self._emit(diagnostics[-1])

        try:
            reconstruction = self._validate_reconstruction(
                record,
                raw_reconstruction,
                diagnostics,
            )
            handler = self._registry.get(record.query_name)
            metadata = self._registry.get_metadata_snapshot(
                record.query_name
            )
            if metadata.query_version != record.query_version:
                raise QueryVersionMismatchError(
                    (
                        "Runtime query version mismatch: "
                        f"historical={record.query_version}, "
                        f"current={metadata.query_version}"
                    ),
                    diagnostics,
                )
            validate_runtime_query_parameters(
                metadata,
                reconstruction.parameter_snapshot,
            )
            request = RuntimeQueryExecutionRequest(
                query_name=reconstruction.query_name,
                parameters=deepcopy(reconstruction.parameter_snapshot),
                execution_context={
                    "verification_of": record.execution_id,
                },
                requested_at=reconstruction.execution_timestamp,
            )
            rebuilt_result = handler.execute(
                request.parameters
            )
            differences = compare_query_results(
                record.result_summary,
                rebuilt_result,
            )
            current_handler_name = type(handler).__name__
            if current_handler_name != reconstruction.handler_name:
                differences.insert(
                    0,
                    QueryDifference(
                        field_path="$.metadata.handler_name",
                        expected_value=reconstruction.handler_name,
                        actual_value=current_handler_name,
                        difference_type="metadata_mismatch",
                    ),
                )
        except QueryVerificationError as exc:
            self._fail(record, diagnostics, str(exc))
            raise
        except RuntimeQueryNotFoundError as exc:
            self._fail(record, diagnostics, str(exc))
            raise
        except Exception as exc:
            message = f"Query verification failed: {exc}"
            self._fail(record, diagnostics, message)
            raise QueryVerificationError(message, diagnostics) from exc

        verified = not differences
        diagnostics.append(
            self._diagnostic(
                EventType.QUERY_VERIFICATION_COMPLETED,
                execution_id=record.execution_id,
                query_name=record.query_name,
                query_version=record.query_version,
                verified=verified,
                difference_count=len(differences),
            )
        )
        self._emit(diagnostics[-1])
        try:
            lineage = self._lineage.generate(record.execution_id)
        except QueryLineageGenerationError:
            lineage = None
        try:
            current_manifest = self._manifests.generate(
                record.execution_id,
                result_summary=record.result_summary,
            )
            rebuilt_manifest = self._manifests.generate(
                record.execution_id,
                result_summary=rebuilt_result,
            )
            hash_match = (
                current_manifest.content_hash
                == rebuilt_manifest.content_hash
            )
        except QueryManifestGenerationError:
            current_manifest = None
            rebuilt_manifest = None
            hash_match = None
        return QueryVerificationResult(
            execution_id=record.execution_id,
            query_name=record.query_name,
            query_version=record.query_version,
            verified=verified,
            verified_at=self._clock(),
            original_result_summary=record.result_summary,
            rebuilt_result_summary=rebuilt_result,
            differences=differences,
            reconstruction_info=reconstruction,
            diagnostics=diagnostics,
            lineage=lineage,
            current_manifest=current_manifest,
            rebuilt_manifest=rebuilt_manifest,
            hash_match=hash_match,
        )

    def _validate_reconstruction(
        self,
        record: QueryExecutionRecord,
        raw_reconstruction: dict[str, Any],
        diagnostics: list[QueryVerificationDiagnostic],
    ) -> QueryReconstructionInfo:
        try:
            reconstruction = QueryReconstructionInfo.model_validate(
                raw_reconstruction
            )
        except ValidationError as exc:
            raise QueryReconstructionMetadataError(
                f"Incomplete query reconstruction metadata: {exc}",
                diagnostics,
            ) from exc
        if (
            reconstruction.query_name != record.query_name
            or reconstruction.query_version != record.query_version
            or reconstruction.handler_name
            != record.execution_metadata.handler_name
            or reconstruction.execution_timestamp != record.executed_at
            or reconstruction.parameter_snapshot != record.parameters
        ):
            raise QueryReconstructionMetadataError(
                "Query reconstruction metadata does not match history record",
                diagnostics,
            )
        return reconstruction

    def _fail(
        self,
        record: QueryExecutionRecord,
        diagnostics: list[QueryVerificationDiagnostic],
        message: str,
    ) -> None:
        diagnostics.append(
            self._diagnostic(
                EventType.QUERY_VERIFICATION_FAILED,
                execution_id=record.execution_id,
                query_name=record.query_name,
                query_version=record.query_version,
                verified=False,
                difference_count=0,
                message=message,
            )
        )
        self._emit(diagnostics[-1], severity=Severity.ERROR)

    @staticmethod
    def _diagnostic(
        event_type: EventType,
        *,
        execution_id: str,
        query_name: str | None,
        query_version: int | None,
        verified: bool,
        difference_count: int,
        message: str | None = None,
    ) -> QueryVerificationDiagnostic:
        return QueryVerificationDiagnostic(
            event_type=event_type.value,
            execution_id=execution_id,
            query_name=query_name,
            query_version=query_version,
            verified=verified,
            difference_count=difference_count,
            message=message,
        )

    def _emit(
        self,
        diagnostic: QueryVerificationDiagnostic,
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


def compare_query_results(
    expected: Any,
    actual: Any,
) -> list[QueryDifference]:
    differences: list[QueryDifference] = []
    _compare_values(
        _normalize_value(expected),
        _normalize_value(actual),
        "$",
        differences,
    )
    return differences


def _normalize_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalize_value(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {
            key: _normalize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    return value


def _compare_values(
    expected: Any,
    actual: Any,
    field_path: str,
    differences: list[QueryDifference],
) -> None:
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(expected.keys() | actual.keys()):
            child_path = f"{field_path}.{key}"
            if key not in actual:
                differences.append(
                    QueryDifference(
                        field_path=child_path,
                        expected_value=expected[key],
                        actual_value=None,
                        difference_type="missing_field",
                    )
                )
            elif key not in expected:
                differences.append(
                    QueryDifference(
                        field_path=child_path,
                        expected_value=None,
                        actual_value=actual[key],
                        difference_type="unexpected_field",
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
                QueryDifference(
                    field_path=f"{field_path}[{index}]",
                    expected_value=expected[index],
                    actual_value=None,
                    difference_type="missing_field",
                )
            )
        for index in range(shared_length, len(actual)):
            differences.append(
                QueryDifference(
                    field_path=f"{field_path}[{index}]",
                    expected_value=None,
                    actual_value=actual[index],
                    difference_type="unexpected_field",
                )
            )
        return

    if expected != actual:
        differences.append(
            QueryDifference(
                field_path=field_path,
                expected_value=expected,
                actual_value=actual,
                difference_type=(
                    "result_summary_mismatch"
                    if field_path == "$"
                    else "value_mismatch"
                ),
            )
        )


query_verification_service = QueryVerificationService()
