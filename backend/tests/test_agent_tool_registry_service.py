import pytest

from app.models.agent_loop import AgentLoopToolCall
from app.services.agent_tool_registry_service import AgentToolRegistryService


def test_observe_tool_returns_observation() -> None:
    result = AgentToolRegistryService().execute(
        AgentLoopToolCall(
            tool="observe",
            arguments={"message": "The input is valid."},
        )
    )

    assert result.tool == "observe"
    assert result.output == "The input is valid."
    assert result.completion_intent is False


def test_final_answer_tool_marks_completion() -> None:
    result = AgentToolRegistryService().execute(
        "final_answer",
        {"answer": "The final response."},
    )

    assert result.output == "The final response."
    assert result.completion_intent is True


def test_unknown_tool_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown agent loop tool"):
        AgentToolRegistryService().execute("shell", {"command": "pwd"})


def test_tool_definitions_are_deterministic_and_self_describing() -> None:
    registry = AgentToolRegistryService()

    tools = registry.list_tools()

    assert [tool.name for tool in tools] == ["final_answer", "observe"]
    assert tools[0].argument_schema["properties"]["answer"] == {
        "type": "string"
    }
    assert tools[0].argument_schema["required"] == ["answer"]
    assert tools[0].argument_schema["additionalProperties"] is False
    assert tools[0].completion_tool is True
    assert tools[1].argument_schema["properties"]["message"] == {
        "type": "string"
    }
    assert tools[1].argument_schema["required"] == ["message"]
    assert tools[1].argument_schema["additionalProperties"] is False
    assert tools[1].completion_tool is False
    assert registry.get_tool("observe") == tools[1]


@pytest.mark.parametrize(
    ("tool", "arguments", "argument"),
    [
        ("observe", {}, "message"),
        ("final_answer", {}, "answer"),
        ("observe", {"message": 1}, "message"),
        ("final_answer", {"answer": False}, "answer"),
    ],
)
def test_required_string_arguments_are_enforced(
    tool: str,
    arguments: dict,
    argument: str,
) -> None:
    with pytest.raises(ValueError, match=rf"argument '{argument}'"):
        AgentToolRegistryService().execute(tool, arguments)


def test_unexpected_arguments_are_rejected_deterministically() -> None:
    with pytest.raises(
        ValueError,
        match=r"unexpected argument\(s\): alpha, zeta",
    ):
        AgentToolRegistryService().execute(
            "observe",
            {
                "message": "Valid observation",
                "zeta": True,
                "alpha": True,
            },
        )
