from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.models.provider_execution import (
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStreamEvent,
)


class ProviderAdapterError(RuntimeError):
    pass


class ProviderAdapter(ABC):
    @abstractmethod
    async def complete(
        self,
        request: ProviderExecutionRequest,
    ) -> ProviderExecutionResult:
        raise NotImplementedError

    @abstractmethod
    async def stream(
        self,
        request: ProviderExecutionRequest,
    ) -> AsyncIterator[ProviderExecutionStreamEvent]:
        if False:
            yield ProviderExecutionStreamEvent(
                provider=request.provider,
                model=request.model,
                event_type="unreachable",
                sequence=0,
            )
        raise NotImplementedError
