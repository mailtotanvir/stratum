import json

from app.models.agent_loop import (
    AgentLoopRequest,
    AgentLoopStep,
    AgentLoopToolCall,
    AgentLoopToolResult,
)
from app.models.provider_execution import ProviderMessageRole
from app.services.agent_loop_prompt_builder_service import (
    AGENT_LOOP_SYSTEM_PROMPT,
    AgentLoopPromptBuilderService,
)


def request() -> AgentLoopRequest:
    return AgentLoopRequest(
        session_id="prompt-session",
        user_request="Answer the question",
    )


def observation(iteration: int, text: str) -> AgentLoopStep:
    provider_output = json.dumps(
        {"tool": "observe", "arguments": {"message": text}}
    )
    return AgentLoopStep(
        iteration=iteration,
        provider_output=provider_output,
        tool_call=AgentLoopToolCall(
            tool="observe",
            arguments={"message": text},
        ),
        tool_result=AgentLoopToolResult(tool="observe", output=text),
    )


def test_builds_system_and_user_messages_for_empty_history() -> None:
    messages = AgentLoopPromptBuilderService().build(request(), [])

    assert [(message.role, message.content) for message in messages] == [
        (ProviderMessageRole.SYSTEM, AGENT_LOOP_SYSTEM_PROMPT),
        (ProviderMessageRole.USER, "Answer the question"),
    ]


def test_builds_single_observation_as_assistant_user_history() -> None:
    step = observation(1, "First observation")

    messages = AgentLoopPromptBuilderService().build(request(), [step])

    assert [(message.role, message.content) for message in messages] == [
        (ProviderMessageRole.SYSTEM, AGENT_LOOP_SYSTEM_PROMPT),
        (ProviderMessageRole.USER, "Answer the question"),
        (ProviderMessageRole.ASSISTANT, step.provider_output),
        (ProviderMessageRole.USER, "First observation"),
    ]


def test_builds_multiple_observations_in_step_order() -> None:
    first = observation(1, "First observation")
    second = observation(2, "Second observation")

    messages = AgentLoopPromptBuilderService().build(
        request(),
        [first, second],
    )

    assert [
        (message.role, message.content) for message in messages[2:]
    ] == [
        (ProviderMessageRole.ASSISTANT, first.provider_output),
        (ProviderMessageRole.USER, "First observation"),
        (ProviderMessageRole.ASSISTANT, second.provider_output),
        (ProviderMessageRole.USER, "Second observation"),
    ]


def test_repeated_builds_are_identical() -> None:
    builder = AgentLoopPromptBuilderService()
    steps = [
        observation(1, "First observation"),
        observation(2, "Second observation"),
    ]

    first = builder.build(request(), steps)
    second = builder.build(request(), steps)

    assert first == second
    assert first is not second


def test_system_prompt_contains_tool_schemas() -> None:
    system_prompt = AgentLoopPromptBuilderService().build(
        request(),
        [],
    )[0].content

    assert '"name": "observe"' in system_prompt
    assert '"message": {"type": "string"}' in system_prompt
    assert '"required": ["message"]' in system_prompt
    assert '"name": "final_answer"' in system_prompt
    assert '"answer": {"type": "string"}' in system_prompt
    assert '"required": ["answer"]' in system_prompt
    assert '"name": "read_file"' in system_prompt
    assert '"name": "list_directory"' in system_prompt
    assert '"path": {"type": "string"}' in system_prompt
