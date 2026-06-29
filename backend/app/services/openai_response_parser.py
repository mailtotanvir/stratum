from copy import deepcopy

from app.models.provider_execution import (
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderUsage,
)
from app.services.openai_protocol_validator import (
    OpenAIProtocolValidationError,
    OpenAIProtocolValidator,
    openai_protocol_validator,
)


class OpenAIResponseParserError(ValueError):
    pass


class OpenAIResponseParser:
    def __init__(
        self,
        validator: OpenAIProtocolValidator | None = None,
    ) -> None:
        self._validator = validator or openai_protocol_validator

    def parse(
        self,
        response_body: dict,
        request: ProviderExecutionRequest,
    ) -> ProviderExecutionResult:
        try:
            response = self._validator.validate_response(response_body)
        except OpenAIProtocolValidationError as exc:
            raise OpenAIResponseParserError(
                "Malformed OpenAI-compatible chat response."
            ) from exc

        choice = response.choices[0]
        metadata = {}
        if response.id is not None:
            metadata["response_id"] = response.id
        if choice.finish_reason is not None:
            metadata["finish_reason"] = choice.finish_reason

        usage = None
        if response.usage is not None:
            usage = ProviderUsage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )

        return ProviderExecutionResult(
            status=ProviderExecutionStatus.COMPLETED,
            provider=request.provider_id,
            model=response.model or request.model,
            content=choice.message.content,
            raw_response=deepcopy(response_body),
            usage=usage,
            metadata=metadata,
        )


openai_response_parser = OpenAIResponseParser()
