import pytest
from pydantic import ValidationError

from app.models.agent_loop import (
    AgentLoopRequest,
    AgentLoopResult,
    AgentLoopStopRequest,
    AgentLoopStatus,
)


def test_agent_loop_request_defaults() -> None:
    request = AgentLoopRequest(
        session_id="session-1",
        user_request="Answer deterministically",
    )

    assert request.max_iterations == 5
    assert request.provider_id is None
    assert request.model is None


def test_agent_loop_result_defaults() -> None:
    result = AgentLoopResult(
        session_id="session-1",
        status=AgentLoopStatus.RUNNING,
        iterations_used=0,
    )

    assert result.final_answer is None
    assert result.steps == []
    assert result.error is None


def test_agent_loop_stop_request_rejects_blank_reason() -> None:
    with pytest.raises(ValidationError):
        AgentLoopStopRequest(reason="   ")
