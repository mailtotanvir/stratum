from pydantic import ValidationError

from app.models.openai_protocol import (
    OpenAIChatRequest,
    OpenAIChatResponse,
    OpenAIChatStreamChunk,
)


class OpenAIProtocolValidationError(ValueError):
    pass


class OpenAIProtocolValidator:
    def validate_request(
        self,
        request: OpenAIChatRequest | dict,
    ) -> OpenAIChatRequest:
        return self._validate(
            OpenAIChatRequest,
            request,
            "request",
        )

    def validate_response(
        self,
        response: OpenAIChatResponse | dict,
    ) -> OpenAIChatResponse:
        return self._validate(
            OpenAIChatResponse,
            response,
            "response",
        )

    def validate_stream_chunk(
        self,
        chunk: OpenAIChatStreamChunk | dict,
    ) -> OpenAIChatStreamChunk:
        return self._validate(
            OpenAIChatStreamChunk,
            chunk,
            "stream chunk",
        )

    @staticmethod
    def _validate(model_type, value, label):
        try:
            return model_type.model_validate(value)
        except ValidationError as exc:
            raise OpenAIProtocolValidationError(
                f"Malformed OpenAI-compatible {label}."
            ) from exc


openai_protocol_validator = OpenAIProtocolValidator()
