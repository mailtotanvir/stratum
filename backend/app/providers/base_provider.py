from abc import ABC, abstractmethod

from app.models.provider_execution import (
    ProviderExecutionRequest,
    ProviderExecutionResult,
)


class BaseProvider(ABC):
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def supported_models(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def supports_streaming(self, model: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def execute(
        self,
        request: ProviderExecutionRequest,
    ) -> ProviderExecutionResult:
        raise NotImplementedError
