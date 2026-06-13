from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.models.runtime_event import EventType, Severity
from app.models.runtime_query import RuntimeQuery
from app.models.runtime_query_execution import (
    RuntimeQueryExecutionDiagnostic,
    RuntimeQueryExecutionMetadata,
    RuntimeQueryExecutionRequest,
    RuntimeQueryExecutionResult,
    RuntimeQueryParameterIssue,
)
from app.query.runtime_query_handler import RuntimeQueryHandler
from app.query.runtime_query_registry import (
    RuntimeQueryNotFoundError,
    RuntimeQueryRegistry,
    runtime_query_registry,
)
from app.services.event_service import EventService, event_service
from app.services.query_history_service import (
    QueryHistoryService,
    query_history_service,
)


class RuntimeQueryParameterValidationError(ValueError):
    def __init__(
        self,
        query_name: str,
        issues: list[RuntimeQueryParameterIssue],
    ) -> None:
        super().__init__(f"Invalid runtime query parameters: {query_name}")
        self.query_name = query_name
        self.issues = issues


class RuntimeQueryExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        query_name: str,
        execution_id: str,
        diagnostics: list[RuntimeQueryExecutionDiagnostic],
    ) -> None:
        super().__init__(message)
        self.query_name = query_name
        self.execution_id = execution_id
        self.diagnostics = diagnostics


class RuntimeQueryExecutionService:
    def __init__(
        self,
        registry: RuntimeQueryRegistry | None = None,
        events: EventService | None = None,
        clock: Callable[[], datetime] | None = None,
        timer: Callable[[], float] | None = None,
        id_factory: Callable[[], str] | None = None,
        history: QueryHistoryService | None = None,
    ) -> None:
        self._registry = registry or runtime_query_registry
        self._events = events or event_service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._timer = timer or perf_counter
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._history = history or (
            query_history_service
            if self._events is event_service
            else QueryHistoryService(self._events)
        )

    def execute(
        self,
        request: RuntimeQueryExecutionRequest,
    ) -> RuntimeQueryExecutionResult:
        execution_id = self._id_factory()
        started_at = self._timer()
        try:
            handler = self._registry.get(request.query_name)
            metadata = self._registry.get_metadata_snapshot(
                request.query_name
            )
        except RuntimeQueryNotFoundError:
            failed = self._diagnostic(
                EventType.RUNTIME_QUERY_EXECUTION_FAILED,
                request.query_name,
                execution_id,
                duration_ms=self._duration_ms(started_at),
                success=False,
            )
            self._emit(failed, severity=Severity.ERROR)
            raise
        started = self._diagnostic(
            EventType.RUNTIME_QUERY_EXECUTION_STARTED,
            request.query_name,
            execution_id,
            duration_ms=0.0,
            success=False,
        )
        self._emit(started)

        try:
            validate_runtime_query_parameters(
                metadata,
                request.parameters,
            )
            result = handler.execute(dict(request.parameters))
        except RuntimeQueryParameterValidationError as exc:
            duration_ms = self._duration_ms(started_at)
            failed = self._diagnostic(
                EventType.RUNTIME_QUERY_EXECUTION_FAILED,
                request.query_name,
                execution_id,
                duration_ms=duration_ms,
                success=False,
            )
            self._emit(failed, severity=Severity.ERROR)
            self._record_history(
                execution_id=execution_id,
                executed_at=self._clock(),
                parameters=request.parameters,
                metadata=metadata,
                handler=handler,
                duration_ms=duration_ms,
                success=False,
                result_summary={
                    "error_type": type(exc).__name__,
                    "issues": [
                        issue.model_dump(mode="json")
                        for issue in exc.issues
                    ],
                },
            )
            raise
        except Exception as exc:
            duration_ms = self._duration_ms(started_at)
            failed = self._diagnostic(
                EventType.RUNTIME_QUERY_EXECUTION_FAILED,
                request.query_name,
                execution_id,
                duration_ms=duration_ms,
                success=False,
            )
            self._emit(failed, severity=Severity.ERROR)
            self._record_history(
                execution_id=execution_id,
                executed_at=self._clock(),
                parameters=request.parameters,
                metadata=metadata,
                handler=handler,
                duration_ms=duration_ms,
                success=False,
                result_summary={
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            raise RuntimeQueryExecutionError(
                f"Runtime query execution failed: {exc}",
                request.query_name,
                execution_id,
                [started, failed],
            ) from exc

        duration_ms = self._duration_ms(started_at)
        completed = self._diagnostic(
            EventType.RUNTIME_QUERY_EXECUTION_COMPLETED,
            request.query_name,
            execution_id,
            duration_ms=duration_ms,
            success=True,
        )
        self._emit(completed)
        self._emit_legacy_executed(metadata, handler)
        executed_at = self._clock()
        execution_metadata = RuntimeQueryExecutionMetadata(
            query_name=metadata.query_name,
            query_version=metadata.query_version,
            handler_name=type(handler).__name__,
            execution_duration_ms=duration_ms,
        )
        execution_result = RuntimeQueryExecutionResult(
            query_name=request.query_name,
            execution_id=execution_id,
            executed_at=executed_at,
            success=True,
            result=result,
            diagnostics=[started, completed],
            execution_metadata=execution_metadata,
        )
        self._history.record_execution(
            execution_id=execution_id,
            executed_at=executed_at,
            parameters=request.parameters,
            execution_metadata=execution_metadata,
            success=True,
            result_summary=result,
        )
        return execution_result

    def _record_history(
        self,
        *,
        execution_id: str,
        executed_at: datetime,
        parameters: dict[str, Any],
        metadata: RuntimeQuery,
        handler: RuntimeQueryHandler,
        duration_ms: float,
        success: bool,
        result_summary: Any,
    ) -> None:
        self._history.record_execution(
            execution_id=execution_id,
            executed_at=executed_at,
            parameters=parameters,
            execution_metadata=RuntimeQueryExecutionMetadata(
                query_name=metadata.query_name,
                query_version=metadata.query_version,
                handler_name=type(handler).__name__,
                execution_duration_ms=duration_ms,
            ),
            success=success,
            result_summary=result_summary,
        )

    def _duration_ms(self, started_at: float) -> float:
        return round(max(0.0, (self._timer() - started_at) * 1000), 3)

    def _diagnostic(
        self,
        event_type: EventType,
        query_name: str,
        execution_id: str,
        duration_ms: float,
        success: bool,
    ) -> RuntimeQueryExecutionDiagnostic:
        return RuntimeQueryExecutionDiagnostic(
            event_type=event_type.value,
            query_name=query_name,
            execution_id=execution_id,
            duration_ms=duration_ms,
            success=success,
        )

    def _emit(
        self,
        diagnostic: RuntimeQueryExecutionDiagnostic,
        severity: Severity = Severity.INFO,
    ) -> None:
        self._events.emit_event_sync(
            event_type=diagnostic.event_type,
            severity=severity,
            message=diagnostic.event_type.replace("_", " ").capitalize(),
            metadata=diagnostic.model_dump(
                mode="json",
                exclude={"event_type"},
            ),
        )

    def _emit_legacy_executed(
        self,
        metadata: RuntimeQuery,
        handler: RuntimeQueryHandler,
    ) -> None:
        self._events.emit_event_sync(
            event_type=EventType.RUNTIME_QUERY_EXECUTED,
            message="Runtime query executed",
            metadata={
                "query_name": metadata.query_name,
                "query_version": metadata.query_version,
                "handler": type(handler).__name__,
            },
        )


def validate_runtime_query_parameters(
    metadata: RuntimeQuery,
    parameters: dict[str, Any],
) -> None:
    issues: list[RuntimeQueryParameterIssue] = []
    supported = metadata.supported_parameters

    for parameter in sorted(parameters.keys() - supported.keys()):
        issues.append(
            RuntimeQueryParameterIssue(
                parameter=parameter,
                error_type="unknown_parameter",
                message=f"Unsupported runtime query parameter: {parameter}",
            )
        )

    for parameter, contract in sorted(supported.items()):
        required = contract.get("required") is True
        if required and parameter not in parameters:
            issues.append(
                RuntimeQueryParameterIssue(
                    parameter=parameter,
                    error_type="missing_parameter",
                    message=f"Required runtime query parameter: {parameter}",
                    expected_type=contract.get("type"),
                )
            )
            continue
        if parameter not in parameters:
            continue

        expected_type = contract.get("type")
        value = parameters[parameter]
        if not _matches_parameter_type(value, expected_type):
            issues.append(
                RuntimeQueryParameterIssue(
                    parameter=parameter,
                    error_type="invalid_parameter_type",
                    message=(
                        f"Invalid type for runtime query parameter: {parameter}"
                    ),
                    expected_type=expected_type,
                    actual_type=_parameter_type_name(value),
                )
            )

    if issues:
        raise RuntimeQueryParameterValidationError(
            metadata.query_name,
            issues,
        )


def _matches_parameter_type(value: Any, expected_type: Any) -> bool:
    type_checks = {
        "array": lambda item: isinstance(item, list),
        "boolean": lambda item: isinstance(item, bool),
        "integer": lambda item: isinstance(item, int)
        and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float))
        and not isinstance(item, bool),
        "object": lambda item: isinstance(item, dict),
        "string": lambda item: isinstance(item, str),
    }
    check = type_checks.get(expected_type)
    return check(value) if check is not None else False


def _parameter_type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return type(value).__name__


runtime_query_execution_service = RuntimeQueryExecutionService()
