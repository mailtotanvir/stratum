import json
from collections.abc import AsyncIterator

from app.models.provider_execution import (
    ProviderExecutionRequest,
    ProviderExecutionStreamEvent,
)
from app.services.openai_protocol_validator import (
    OpenAIProtocolValidationError,
    OpenAIProtocolValidator,
    openai_protocol_validator,
)


class OpenAIStreamParserError(ValueError):
    pass


class OpenAIStreamParser:
    def __init__(
        self,
        validator: OpenAIProtocolValidator | None = None,
    ) -> None:
        self._validator = validator or openai_protocol_validator

    async def parse(
        self,
        chunks: AsyncIterator[bytes],
        request: ProviderExecutionRequest,
    ) -> AsyncIterator[ProviderExecutionStreamEvent]:
        sequence = 0
        completed = False

        async for raw_chunk in chunks:
            payload = _decode_chunk(raw_chunk)
            if payload is None:
                if not completed:
                    yield _completed_event(request, sequence)
                    sequence += 1
                    completed = True
                continue
            if completed:
                raise OpenAIStreamParserError(
                    "Received stream data after completion."
                )

            try:
                chunk = self._validator.validate_stream_chunk(payload)
            except OpenAIProtocolValidationError as exc:
                raise OpenAIStreamParserError(
                    "Malformed OpenAI-compatible stream chunk."
                ) from exc

            choice = chunk.choices[0]
            model = chunk.model or request.model
            metadata = {}
            if chunk.id is not None:
                metadata["response_id"] = chunk.id

            if choice.delta.content is not None or (
                choice.finish_reason is None
            ):
                yield ProviderExecutionStreamEvent(
                    provider=request.provider_id,
                    model=model,
                    event_type="delta",
                    sequence=sequence,
                    content=choice.delta.content,
                    metadata=dict(metadata),
                )
                sequence += 1

            if choice.finish_reason is not None:
                metadata["finish_reason"] = choice.finish_reason
                yield ProviderExecutionStreamEvent(
                    provider=request.provider_id,
                    model=model,
                    event_type="completed",
                    sequence=sequence,
                    done=True,
                    metadata=metadata,
                )
                sequence += 1
                completed = True


def _decode_chunk(raw_chunk: bytes) -> dict | None:
    try:
        text = raw_chunk.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise OpenAIStreamParserError(
            "Malformed OpenAI-compatible stream chunk."
        ) from exc
    if text.startswith("data:"):
        text = text[5:].strip()
    if text == "[DONE]":
        return None
    if not text:
        raise OpenAIStreamParserError(
            "Malformed OpenAI-compatible stream chunk."
        )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OpenAIStreamParserError(
            "Malformed OpenAI-compatible stream chunk."
        ) from exc
    if not isinstance(payload, dict):
        raise OpenAIStreamParserError(
            "Malformed OpenAI-compatible stream chunk."
        )
    return payload


def _completed_event(
    request: ProviderExecutionRequest,
    sequence: int,
) -> ProviderExecutionStreamEvent:
    return ProviderExecutionStreamEvent(
        provider=request.provider_id,
        model=request.model,
        event_type="completed",
        sequence=sequence,
        done=True,
    )


openai_stream_parser = OpenAIStreamParser()
