from typing import Any

from app.models.projection import (
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.models.runtime_event import EventType, RuntimeEvent
from app.models.session_agent_execution_projection import (
    SessionAgentExecutionItem,
    SessionAgentExecutionProjection,
)
from app.services.event_service import EventService, event_service


SESSION_AGENT_EXECUTION_PROJECTION_TYPE = (
    "session_agent_execution_projection"
)
SESSION_AGENT_EXECUTION_PROJECTION_SCHEMA_VERSION = 1

AGENT_EVENT_TYPES = {
    EventType.AGENT_EXECUTION_REQUESTED,
    EventType.AGENT_EXECUTION_STARTED,
    EventType.AGENT_EXECUTION_COMPLETED,
    EventType.AGENT_EXECUTION_FAILED,
}
PROVIDER_EVENT_TYPES = {
    EventType.PROVIDER_EXECUTION_REQUESTED,
    EventType.PROVIDER_EXECUTION_STARTED,
    EventType.PROVIDER_EXECUTION_COMPLETED,
    EventType.PROVIDER_EXECUTION_FAILED,
}


class SessionAgentExecutionProjectionBuilderService:
    schema_info = ProjectionSchemaInfo(
        projection_type=SESSION_AGENT_EXECUTION_PROJECTION_TYPE,
        schema_version=SESSION_AGENT_EXECUTION_PROJECTION_SCHEMA_VERSION,
        builder_name="SessionAgentExecutionProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=SESSION_AGENT_EXECUTION_PROJECTION_TYPE,
            reconstruction_source="runtime_event_store",
            authoritative_source="runtime_event_store",
        ),
    )
    projection_type = SESSION_AGENT_EXECUTION_PROJECTION_TYPE

    def __init__(self, events: EventService | None = None) -> None:
        self._events = events or event_service

    def build(
        self,
        runtime_session_id: str,
    ) -> SessionAgentExecutionProjection:
        events = [
            event
            for event in self._events.list_persisted_events()
            if event.metadata.get("runtime_session_id")
            == runtime_session_id
            and event.type in AGENT_EVENT_TYPES | PROVIDER_EVENT_TYPES
        ]
        state = _ProjectionState()
        for index, event in enumerate(events):
            if event.type in AGENT_EVENT_TYPES:
                state.apply_agent_event(event, index)
            else:
                state.apply_provider_event(event, index)

        return SessionAgentExecutionProjection(
            runtime_session_id=runtime_session_id,
            executions=state.items(),
            total_agent_executions=len(state.agent_ids),
            completed_agent_executions=len(state.completed_agent_ids),
            failed_agent_executions=len(state.failed_agent_ids),
            total_provider_executions=len(state.provider_ids),
            completed_provider_executions=len(
                state.completed_provider_ids
            ),
            failed_provider_executions=len(state.failed_provider_ids),
            metadata={},
        )


class _ProjectionState:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._first_indexes: dict[str, int] = {}
        self._agent_keys: dict[str, str] = {}
        self._provider_keys: dict[str, str] = {}
        self._correlation_keys: dict[str, str] = {}
        self.agent_ids: set[str] = set()
        self.completed_agent_ids: set[str] = set()
        self.failed_agent_ids: set[str] = set()
        self.provider_ids: set[str] = set()
        self.completed_provider_ids: set[str] = set()
        self.failed_provider_ids: set[str] = set()

    def apply_agent_event(
        self,
        event: RuntimeEvent,
        index: int,
    ) -> None:
        metadata = event.metadata
        agent_id = _text(metadata.get("agent_execution_id"))
        if agent_id is None:
            return
        self.agent_ids.add(agent_id)
        key = self._agent_keys.get(agent_id, f"agent:{agent_id}")
        key = self._ensure_item(key, index)
        self._agent_keys[agent_id] = key

        correlation_id = _text(metadata.get("correlation_id"))
        if correlation_id is not None:
            key = self._merge_correlation(key, correlation_id)
        provider_id = _provider_execution_id(metadata)
        if provider_id is not None:
            self.provider_ids.add(provider_id)
            key = self._merge_provider(key, provider_id)

        item = self._items[key]
        item["agent_execution_id"] = agent_id
        _copy_identity(item, metadata)
        _apply_event_status(item, event, agent=True)
        if provider_id is not None:
            item["provider_execution_id"] = provider_id
        if correlation_id is not None:
            item["correlation_id"] = correlation_id

        if event.type == EventType.AGENT_EXECUTION_COMPLETED:
            self.completed_agent_ids.add(agent_id)
            if provider_id is not None:
                self.completed_provider_ids.add(provider_id)
        elif event.type == EventType.AGENT_EXECUTION_FAILED:
            self.failed_agent_ids.add(agent_id)
            if provider_id is not None:
                self.failed_provider_ids.add(provider_id)

    def apply_provider_event(
        self,
        event: RuntimeEvent,
        index: int,
    ) -> None:
        metadata = event.metadata
        provider_id = _provider_execution_id(metadata)
        if provider_id is None:
            return
        self.provider_ids.add(provider_id)
        correlation_id = _text(metadata.get("correlation_id"))
        key = self._provider_keys.get(provider_id)
        if key is None and correlation_id is not None:
            key = self._correlation_keys.get(correlation_id)
        if key is None:
            key = f"provider:{provider_id}"
        key = self._ensure_item(key, index)
        self._provider_keys[provider_id] = key
        if correlation_id is not None:
            self._correlation_keys[correlation_id] = key

        item = self._items[key]
        item["provider_execution_id"] = provider_id
        _copy_identity(item, metadata)
        _apply_event_status(item, event, agent=False)
        if correlation_id is not None:
            item["correlation_id"] = correlation_id
        usage = metadata.get("usage")
        if isinstance(usage, dict):
            item["usage"] = dict(usage)
        error_message = _text(metadata.get("error_message"))
        if error_message is not None:
            item["error_message"] = error_message

        if event.type == EventType.PROVIDER_EXECUTION_COMPLETED:
            self.completed_provider_ids.add(provider_id)
        elif event.type == EventType.PROVIDER_EXECUTION_FAILED:
            self.failed_provider_ids.add(provider_id)

    def items(self) -> list[SessionAgentExecutionItem]:
        keys = sorted(
            self._items,
            key=lambda key: (
                self._first_indexes[key],
                key,
            ),
        )
        return [
            SessionAgentExecutionItem(**self._items[key])
            for key in keys
        ]

    def _ensure_item(self, key: str, index: int) -> str:
        if key not in self._items:
            self._items[key] = {
                "status": "pending",
                "metadata": {},
            }
            self._first_indexes[key] = index
        return key

    def _merge_correlation(
        self,
        agent_key: str,
        correlation_id: str,
    ) -> str:
        existing_key = self._correlation_keys.get(correlation_id)
        if existing_key is not None and existing_key != agent_key:
            agent_key = self._merge_items(agent_key, existing_key)
        self._correlation_keys[correlation_id] = agent_key
        return agent_key

    def _merge_provider(
        self,
        agent_key: str,
        provider_id: str,
    ) -> str:
        existing_key = self._provider_keys.get(provider_id)
        if existing_key is not None and existing_key != agent_key:
            agent_key = self._merge_items(agent_key, existing_key)
        self._provider_keys[provider_id] = agent_key
        return agent_key

    def _merge_items(self, target_key: str, source_key: str) -> str:
        target = self._items[target_key]
        source = self._items[source_key]
        for field, value in source.items():
            if field == "metadata":
                continue
            if target.get(field) is None:
                target[field] = value
        self._first_indexes[target_key] = min(
            self._first_indexes[target_key],
            self._first_indexes[source_key],
        )
        del self._items[source_key]
        del self._first_indexes[source_key]
        for mapping in (
            self._agent_keys,
            self._provider_keys,
            self._correlation_keys,
        ):
            for identity, key in list(mapping.items()):
                if key == source_key:
                    mapping[identity] = target_key
        return target_key


def _copy_identity(
    item: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    for field in (
        "provider",
        "model",
        "task_id",
        "correlation_id",
    ):
        value = _text(metadata.get(field))
        if value is not None:
            item[field] = value


def _apply_event_status(
    item: dict[str, Any],
    event: RuntimeEvent,
    *,
    agent: bool,
) -> None:
    if event.type in {
        EventType.AGENT_EXECUTION_STARTED,
        EventType.PROVIDER_EXECUTION_STARTED,
    }:
        item["status"] = "running"
        item["started_at"] = item.get("started_at") or event.ts
    elif event.type in {
        EventType.AGENT_EXECUTION_COMPLETED,
        EventType.PROVIDER_EXECUTION_COMPLETED,
    }:
        item["status"] = "completed"
        item["completed_at"] = event.ts
    elif event.type in {
        EventType.AGENT_EXECUTION_FAILED,
        EventType.PROVIDER_EXECUTION_FAILED,
    }:
        item["status"] = "failed"
        item["completed_at"] = event.ts
    elif agent:
        item["status"] = "pending"
    else:
        item["status"] = "requested"


def _provider_execution_id(metadata: dict[str, Any]) -> str | None:
    return _text(
        metadata.get("provider_execution_id")
        or metadata.get("provider_execution_record_id")
    )


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


session_agent_execution_projection_builder_service = (
    SessionAgentExecutionProjectionBuilderService()
)
