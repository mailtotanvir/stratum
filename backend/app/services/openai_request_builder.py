from app.models.openai_request import (
    OpenAIChatMessage,
    OpenAIChatRequest,
)
from app.models.provider_execution import (
    ProviderExecutionRequest,
    ProviderStreamMode,
)


class OpenAIRequestBuilder:
    def build(
        self,
        request: ProviderExecutionRequest,
    ) -> OpenAIChatRequest:
        return OpenAIChatRequest(
            model=request.model,
            messages=[
                OpenAIChatMessage(
                    role=message.role,
                    content=message.content,
                    name=message.name,
                    tool_call_id=message.tool_call_id,
                )
                for message in request.messages
            ],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=request.stream_mode != ProviderStreamMode.NONE,
        )


openai_request_builder = OpenAIRequestBuilder()
