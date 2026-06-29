from copy import deepcopy

import pytest

from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionStatus,
    ProviderMessage,
    ProviderMessageRole,
)
from app.services.openai_response_parser import (
    OpenAIResponseParser,
    OpenAIResponseParserError,
)


def execution_request() -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider="openai-compatible",
        model="request-model",
        mode=ProviderExecutionMode.CHAT,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Parse the response.",
            )
        ],
    )


def response_body() -> dict:
    return {
        "id": "chatcmpl-1",
        "model": "response-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Parsed response.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 7,
            "completion_tokens": 3,
            "total_tokens": 10,
        },
    }


def test_parses_minimal_valid_assistant_response() -> None:
    body = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Minimal response.",
                }
            }
        ]
    }

    result = OpenAIResponseParser().parse(body, execution_request())

    assert result.status == ProviderExecutionStatus.COMPLETED
    assert result.content == "Minimal response."
    assert result.raw_response == body


def test_preserves_provider_id_from_request() -> None:
    result = OpenAIResponseParser().parse(
        response_body(),
        execution_request(),
    )

    assert result.provider == "openai-compatible"


def test_uses_response_model_when_present() -> None:
    result = OpenAIResponseParser().parse(
        response_body(),
        execution_request(),
    )

    assert result.model == "response-model"


def test_falls_back_to_request_model() -> None:
    body = response_body()
    body.pop("model")

    result = OpenAIResponseParser().parse(body, execution_request())

    assert result.model == "request-model"


def test_maps_usage() -> None:
    result = OpenAIResponseParser().parse(
        response_body(),
        execution_request(),
    )

    assert result.usage is not None
    assert result.usage.input_tokens == 7
    assert result.usage.output_tokens == 3
    assert result.usage.total_tokens == 10


def test_stores_response_id_and_finish_reason_in_metadata() -> None:
    result = OpenAIResponseParser().parse(
        response_body(),
        execution_request(),
    )

    assert result.metadata == {
        "response_id": "chatcmpl-1",
        "finish_reason": "stop",
    }


def test_missing_choices_raises_parser_error() -> None:
    with pytest.raises(
        OpenAIResponseParserError,
        match="Malformed OpenAI-compatible chat response",
    ):
        OpenAIResponseParser().parse({}, execution_request())


@pytest.mark.parametrize(
    "choice",
    [
        {},
        {"message": {"role": "assistant"}},
        {
            "message": {
                "role": "assistant",
                "content": "",
            }
        },
    ],
)
def test_missing_message_or_content_raises_parser_error(
    choice: dict,
) -> None:
    with pytest.raises(OpenAIResponseParserError):
        OpenAIResponseParser().parse(
            {"choices": [choice]},
            execution_request(),
        )


def test_input_response_dict_is_not_mutated() -> None:
    body = response_body()
    before = deepcopy(body)

    result = OpenAIResponseParser().parse(body, execution_request())
    result.raw_response["choices"][0]["message"]["content"] = "Changed"

    assert body == before


def test_provider_execution_request_is_not_mutated() -> None:
    request = execution_request()
    before = request.model_dump(mode="json")

    OpenAIResponseParser().parse(response_body(), request)

    assert request.model_dump(mode="json") == before


def test_model_dump_output_is_deterministic() -> None:
    parser = OpenAIResponseParser()
    request = execution_request()
    body = response_body()

    first = parser.parse(body, request)
    second = parser.parse(body, request)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
