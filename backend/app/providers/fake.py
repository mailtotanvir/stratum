from collections.abc import AsyncIterator

from app.models.provider_execution import (
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderExecutionStreamEvent,
    ProviderUsage,
)
from app.providers.base import ProviderAdapter, ProviderAdapterError


FAKE_PROVIDER_ID = "fake"
FAKE_RESPONSE_CONTENT = "Fake provider response."


class FakeProviderAdapter(ProviderAdapter):
    provider_id = FAKE_PROVIDER_ID

    async def complete(
        self,
        request: ProviderExecutionRequest,
    ) -> ProviderExecutionResult:
        _raise_if_simulated_error(request)
        return ProviderExecutionResult(
            status=ProviderExecutionStatus.COMPLETED,
            provider=self.provider_id,
            model=request.model,
            content=FAKE_RESPONSE_CONTENT,
            raw_response={
                "fake": True,
                "content": FAKE_RESPONSE_CONTENT,
            },
            usage=ProviderUsage(
                input_tokens=_input_tokens(request),
                output_tokens=3,
                estimated_cost=0,
            ),
            latency_ms=0,
            metadata={
                "provider_id": self.provider_id,
                "model": request.model,
                "deterministic": True,
            },
        )

    async def stream(
        self,
        request: ProviderExecutionRequest,
    ) -> AsyncIterator[ProviderExecutionStreamEvent]:
        _raise_if_simulated_error(request)
        common = {
            "provider": self.provider_id,
            "model": request.model,
            "metadata": {
                "provider_id": self.provider_id,
                "deterministic": True,
            },
        }
        yield ProviderExecutionStreamEvent(
            **common,
            event_type="start",
            sequence=0,
        )
        yield ProviderExecutionStreamEvent(
            **common,
            event_type="delta",
            sequence=1,
            content=FAKE_RESPONSE_CONTENT,
        )
        yield ProviderExecutionStreamEvent(
            **common,
            event_type="completed",
            sequence=2,
            done=True,
        )


def _raise_if_simulated_error(
    request: ProviderExecutionRequest,
) -> None:
    if request.metadata.get("simulate_error") is True:
        raise ProviderAdapterError("Simulated fake provider failure.")


def _input_tokens(request: ProviderExecutionRequest) -> int:
    return sum(
        len(message.content.split())
        for message in request.messages
    )
