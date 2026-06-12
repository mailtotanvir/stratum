from typing import Any, Protocol, runtime_checkable

from app.models.runtime_query import RuntimeQuery


@runtime_checkable
class RuntimeQueryHandler(Protocol):
    def metadata(self) -> RuntimeQuery:
        """Return the stable query discovery contract."""

    def execute(self, parameters: dict[str, Any]) -> Any:
        """Execute a read-only query against authoritative or derived state."""
