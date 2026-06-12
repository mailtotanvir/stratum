from collections.abc import Callable
from datetime import UTC, datetime

from app.models.runtime_event import EventType
from app.models.runtime_query import (
    RuntimeQuery,
    RuntimeQueryDiagnostic,
)
from app.query.runtime_query_handler import RuntimeQueryHandler
from app.query.session_decision_summary_query import (
    session_decision_summary_query,
)
from app.services.event_service import EventService, event_service


class RuntimeQueryAlreadyRegisteredError(ValueError):
    pass


class RuntimeQueryNotFoundError(LookupError):
    pass


class RuntimeQueryContractError(ValueError):
    pass


class RuntimeQueryRegistry:
    def __init__(
        self,
        events: EventService | None = None,
        clock: Callable[[], datetime] | None = None,
        emit_registration_diagnostics: bool = True,
    ) -> None:
        self._handlers: dict[str, RuntimeQueryHandler] = {}
        self._metadata: dict[str, RuntimeQuery] = {}
        self._events = events or event_service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._emit_registration_diagnostics = emit_registration_diagnostics

    def register(self, handler: RuntimeQueryHandler) -> None:
        try:
            metadata = RuntimeQuery.model_validate(handler.metadata())
        except Exception as exc:
            raise RuntimeQueryContractError(
                "Invalid runtime query contract"
            ) from exc

        query_name = metadata.query_name
        if query_name in self._handlers:
            raise RuntimeQueryAlreadyRegisteredError(
                f"Runtime query already registered: {query_name}"
            )
        self._handlers[query_name] = handler
        self._metadata[query_name] = metadata.model_copy(deep=True)
        if self._emit_registration_diagnostics:
            self._emit(
                EventType.RUNTIME_QUERY_REGISTERED,
                metadata,
                handler,
            )

    def get(self, query_name: str) -> RuntimeQueryHandler:
        try:
            return self._handlers[query_name]
        except KeyError as exc:
            raise RuntimeQueryNotFoundError(
                f"Runtime query not found: {query_name}"
            ) from exc

    def get_metadata(self, query_name: str) -> RuntimeQuery:
        handler = self.get(query_name)
        metadata = self.get_metadata_snapshot(query_name)
        self._emit(
            EventType.RUNTIME_QUERY_DISCOVERED,
            metadata,
            handler,
        )
        return metadata

    def get_metadata_snapshot(self, query_name: str) -> RuntimeQuery:
        self.get(query_name)
        return self._metadata[query_name].model_copy(deep=True)

    def list_queries(self) -> list[RuntimeQuery]:
        return [
            self.get_metadata(query_name)
            for query_name in sorted(self._handlers)
        ]

    def _emit(
        self,
        event_type: EventType,
        metadata: RuntimeQuery,
        handler: RuntimeQueryHandler,
    ) -> None:
        self._emit_diagnostic(
            self._diagnostic(event_type, metadata, handler)
        )

    def _diagnostic(
        self,
        event_type: EventType,
        metadata: RuntimeQuery,
        handler: RuntimeQueryHandler,
    ) -> RuntimeQueryDiagnostic:
        return RuntimeQueryDiagnostic(
            event_type=event_type.value,
            query_name=metadata.query_name,
            query_version=metadata.query_version,
            handler=type(handler).__name__,
        )

    def _emit_diagnostic(
        self,
        diagnostic: RuntimeQueryDiagnostic,
    ) -> None:
        self._events.emit_event_sync(
            event_type=diagnostic.event_type,
            message=diagnostic.event_type.replace("_", " ").capitalize(),
            metadata=diagnostic.model_dump(
                mode="json",
                exclude={"event_type"},
            ),
        )


runtime_query_registry = RuntimeQueryRegistry(
    emit_registration_diagnostics=False,
)
runtime_query_registry.register(session_decision_summary_query)
