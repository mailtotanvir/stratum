import json

import httpx

from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionStatus,
    ProviderMessage,
    ProviderMessageRole,
)
from app.providers.openai_compatible_provider import (
    OpenAICompatibleProvider,
)
from app.providers.provider_registry import provider_registry


class SequenceClock:
    def __init__(self, *values: float) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


def execution_request() -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider="openai-compatible",
        model="test-model",
        mode=ProviderExecutionMode.CHAT,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.SYSTEM,
                content="Respond concisely.",
            ),
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Hello provider",
                name="operator",
            ),
        ],
        temperature=0.25,
        max_tokens=64,
    )


def success_payload() -> dict:
    return {
        "id": "chatcmpl-test",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Compatible response.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 8,
            "completion_tokens": 3,
            "total_tokens": 11,
        },
    }


def provider(
    handler,
    *,
    clock: SequenceClock | None = None,
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        provider_name="openai-compatible",
        base_url="https://provider.example/v1/",
        api_key="secret-key",
        default_headers={"X-Client": "stratum"},
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=clock or SequenceClock(1.0, 1.01),
    )


def test_successful_completion_maps_request_and_response() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json=success_payload())

    result = provider(handler).execute(execution_request())

    assert result.status == ProviderExecutionStatus.COMPLETED
    assert result.provider == "openai-compatible"
    assert result.model == "test-model"
    assert result.content == "Compatible response."
    assert result.raw_response == success_payload()
    assert captured["url"] == (
        "https://provider.example/v1/chat/completions"
    )
    assert captured["headers"]["authorization"] == "Bearer secret-key"
    assert captured["headers"]["x-client"] == "stratum"
    assert captured["payload"] == {
        "model": "test-model",
        "messages": [
            {"role": "system", "content": "Respond concisely."},
            {
                "role": "user",
                "content": "Hello provider",
                "name": "operator",
            },
        ],
        "stream": False,
        "temperature": 0.25,
        "max_tokens": 64,
    }


def test_usage_is_parsed() -> None:
    adapter = provider(
        lambda request: httpx.Response(200, json=success_payload())
    )

    result = adapter.execute(execution_request())

    assert result.usage is not None
    assert result.usage.input_tokens == 8
    assert result.usage.output_tokens == 3
    assert result.usage.total_tokens == 11


def test_timeout_returns_failed_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    result = provider(handler).execute(execution_request())

    assert result.status == ProviderExecutionStatus.FAILED
    assert result.error_message == "Provider request timed out."
    assert result.metadata["error_type"] == "timeout"


def test_http_500_returns_failed_result() -> None:
    result = provider(
        lambda request: httpx.Response(
            500,
            json={"error": {"message": "internal error"}},
        )
    ).execute(execution_request())

    assert result.status == ProviderExecutionStatus.FAILED
    assert result.error_message == "Provider returned HTTP 500."
    assert result.metadata["status_code"] == 500


def test_invalid_json_returns_failed_result() -> None:
    result = provider(
        lambda request: httpx.Response(
            200,
            content=b"{not-json",
            headers={"Content-Type": "application/json"},
        )
    ).execute(execution_request())

    assert result.status == ProviderExecutionStatus.FAILED
    assert result.error_message == "Provider returned invalid JSON."
    assert result.metadata["error_type"] == "invalid_json"


def test_malformed_response_returns_failed_result() -> None:
    result = provider(
        lambda request: httpx.Response(
            200,
            json={"choices": "not-a-list"},
        )
    ).execute(execution_request())

    assert result.status == ProviderExecutionStatus.FAILED
    assert result.metadata["error_type"] == "malformed_response"


def test_missing_content_returns_failed_result() -> None:
    result = provider(
        lambda request: httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant"}}]},
        )
    ).execute(execution_request())

    assert result.status == ProviderExecutionStatus.FAILED
    assert result.error_message == (
        "Provider response is missing assistant content."
    )


def test_latency_is_populated_from_injected_clock() -> None:
    result = provider(
        lambda request: httpx.Response(200, json=success_payload()),
        clock=SequenceClock(10.0, 10.025),
    ).execute(execution_request())

    assert result.latency_ms == 25


def test_response_parsing_is_deterministic() -> None:
    adapter = provider(
        lambda request: httpx.Response(200, json=success_payload()),
        clock=SequenceClock(1.0, 1.01, 2.0, 2.01),
    )

    first = adapter.execute(execution_request())
    second = adapter.execute(execution_request())

    assert first == second


def test_adapter_is_registered_without_replacing_mock() -> None:
    assert provider_registry.providers() == [
        "mock",
        "openai-compatible",
    ]
    assert provider_registry.provider("mock").provider_name() == "mock"
    assert (
        provider_registry.provider("openai-compatible").provider_name()
        == "openai-compatible"
    )
