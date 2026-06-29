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

        async for payload in _decode_sse_payloads(chunks):
            if payload is None:
                if not completed:
                    yield _completed_event(request, sequence)
                    sequence += 1
                    completed = True
                continue

            if completed:
                continue

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


async def _decode_sse_payloads(
    chunks: AsyncIterator[bytes],
) -> AsyncIterator[dict | None]:
    buffer = ""

    async for raw_chunk in chunks:
        try:
            text = raw_chunk.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise OpenAIStreamParserError(
                "Malformed OpenAI-compatible stream chunk."
            ) from exc

        if not buffer and "\n\n" not in text and _looks_like_json(text):
            yield _decode_json_payload(text)
            continue

        buffer += text

        while "\n\n" in buffer:
            event_text, buffer = buffer.split("\n\n", 1)
            payload = _decode_sse_event(event_text)
            if payload is _EMPTY_EVENT:
                continue
            yield payload

    if buffer.strip():
        if _looks_like_json(buffer):
            yield _decode_json_payload(buffer)
            return
        payload = _decode_sse_event(buffer)
        if payload is _EMPTY_EVENT:
            raise OpenAIStreamParserError(
                "Malformed OpenAI-compatible stream chunk."
            )
        yield payload


_EMPTY_EVENT = object()


def _looks_like_json(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("{") or stripped.startswith("[")


def _decode_json_payload(text: str) -> dict:
    stripped = text.strip()
    if not stripped:
        raise OpenAIStreamParserError(
            "Malformed OpenAI-compatible stream chunk."
        )
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise OpenAIStreamParserError(
            "Malformed OpenAI-compatible stream chunk."
        ) from exc
    if not isinstance(payload, dict):
        raise OpenAIStreamParserError(
            "Malformed OpenAI-compatible stream chunk."
        )
    return payload


def _decode_sse_event(event_text: str) -> dict | None | object:
    data_lines: list[str] = []
    for line in event_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(":"):
            continue
        if stripped.startswith("data:"):
            data_lines.append(stripped[5:].strip())

    if not data_lines:
        return _EMPTY_EVENT

    text = "\n".join(data_lines).strip()
    if text == "[DONE]":
        return None
    if not text:
        return _EMPTY_EVENT

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
