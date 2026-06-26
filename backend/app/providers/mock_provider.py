from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderUsage,
)
from app.providers.base_provider import BaseProvider


MOCK_PROVIDER_NAME = "mock"
MOCK_SMALL_MODEL = "mock-small"
MOCK_LARGE_MODEL = "mock-large"
MOCK_SUPPORTED_MODELS = [MOCK_SMALL_MODEL, MOCK_LARGE_MODEL]


class MockProvider(BaseProvider):
    def provider_name(self) -> str:
        return MOCK_PROVIDER_NAME

    def supported_models(self) -> list[str]:
        return list(MOCK_SUPPORTED_MODELS)

    def supports_streaming(self, model: str) -> bool:
        return model == MOCK_LARGE_MODEL

    def execute(
        self,
        request: ProviderExecutionRequest,
    ) -> ProviderExecutionResult:
        return ProviderExecutionResult(
            status=ProviderExecutionStatus.COMPLETED,
            provider=request.provider,
            model=request.model,
            content=_content_for_mode(request.mode),
            raw_response={"mock": True},
            usage=ProviderUsage(
                input_tokens=_input_tokens(request),
                output_tokens=2,
                estimated_cost=0,
            ),
            latency_ms=1,
            metadata={"provider": self.provider_name()},
        )


def _content_for_mode(mode: ProviderExecutionMode) -> str:
    if mode == ProviderExecutionMode.CHAT:
        return "Mock response."
    if mode == ProviderExecutionMode.COMPLETION:
        return "Mock completion."
    return "Mock tool call."


def _input_tokens(request: ProviderExecutionRequest) -> int:
    return sum(
        len(message.content.split())
        for message in request.messages
    )
