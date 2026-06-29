import json

from app.models.agent_loop import AgentLoopRequest, AgentLoopStep
from app.models.provider_execution import ProviderMessage, ProviderMessageRole
from app.services.agent_tool_registry_service import (
    AgentToolRegistryService,
    agent_tool_registry_service,
)


def _system_prompt(tools: AgentToolRegistryService) -> str:
    tool_definitions = "\n".join(
        json.dumps(tool.model_dump(), sort_keys=True)
        for tool in tools.list_tools()
    )
    return f"""You are the deterministic reasoning engine for Stratum.

Return exactly one of these JSON objects:
{{"tool":"final_answer","arguments":{{"answer":"..."}}}}
{{"tool":"observe","arguments":{{"message":"..."}}}}

Valid tools:
{tool_definitions}

Return only the JSON object.
Do not use markdown or code fences.
Do not emit prose outside the JSON object."""


AGENT_LOOP_SYSTEM_PROMPT = _system_prompt(agent_tool_registry_service)


class AgentLoopPromptBuilderService:
    def __init__(
        self,
        tools: AgentToolRegistryService | None = None,
    ) -> None:
        self._tools = (
            tools if tools is not None else agent_tool_registry_service
        )

    def build(
        self,
        request: AgentLoopRequest,
        steps: list[AgentLoopStep],
    ) -> list[ProviderMessage]:
        messages = [
            ProviderMessage(
                role=ProviderMessageRole.SYSTEM,
                content=_system_prompt(self._tools),
            ),
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content=request.user_request,
            ),
        ]

        for step in steps:
            if (
                step.provider_output is None
                or step.tool_call is None
                or step.tool_call.tool != "observe"
                or step.tool_result is None
                or step.tool_result.tool != "observe"
            ):
                continue
            messages.extend(
                [
                    ProviderMessage(
                        role=ProviderMessageRole.ASSISTANT,
                        content=step.provider_output,
                    ),
                    ProviderMessage(
                        role=ProviderMessageRole.USER,
                        content=step.tool_result.output,
                    ),
                ]
            )

        return messages


agent_loop_prompt_builder_service = AgentLoopPromptBuilderService()
