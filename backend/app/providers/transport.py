from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pydantic import BaseModel, ConfigDict, Field


class TransportError(RuntimeError):
    pass


class TransportRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    destination: str = Field(min_length=1)
    payload: bytes = b""
    metadata: dict = Field(default_factory=dict)


class TransportResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    payload: bytes = b""
    metadata: dict = Field(default_factory=dict)


class Transport(ABC):
    @abstractmethod
    async def send(
        self,
        request: TransportRequest,
    ) -> TransportResponse:
        raise NotImplementedError

    @abstractmethod
    async def stream(
        self,
        request: TransportRequest,
    ) -> AsyncIterator[bytes]:
        if False:
            yield b""
        raise NotImplementedError
