import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.cognitive_state import CognitiveState
from app.models.planner import PlannerRequest
from app.models.planning_context import (
    PlanningContext,
    PlanningDiagnosticsSummary,
)
from app.models.tool import Tool
from app.planner.mock import MockPlannerAdapter
from app.routes import runtime as runtime_routes
from app.services.planner_input_builder_service import PlannerInputBuilderService
from app.services.runtime_session_service import runtime_session_service
from app.services.tool_registry_service import tool_registry_service


class FakeSessions:
    def get_session(self, session_id: str):
        return SimpleNamespace(id=session_id, task_id="builder-task")


class FakePlanningContext:
    def __init__(self, planning_context: PlanningContext) -> None:
        self.planning_context = planning_context

    def build(self, session_id: str) -> PlanningContext:
        assert session_id == self.planning_context.session_id
        return self.planning_context


class FakeCognitiveState:
    def __init__(self, state: CognitiveState) -> None:
        self.state = state
        self.received_context: PlanningContext | None = None

    def build(
        self,
        session_id: str,
        planning_context: PlanningContext | None = None,
    ) -> CognitiveState:
        assert session_id == self.state.session_id
        self.received_context = planning_context
        return self.state


class FakeTools:
    def __init__(self, records) -> None:
        self.records = records

    def list_tools(self, enabled_only: bool = False):
        assert enabled_only is True
        return self.records

    def list_parameters(self, tool_id: str):
        return []


def builder_tool_record():
    return SimpleNamespace(
        id="builder-tool",
        name="shell.read",
        description="Read files",
        enabled=True,
        created_at=SimpleNamespace(isoformat=lambda: "2026-06-07T00:00:00+00:00"),
        updated_at=SimpleNamespace(isoformat=lambda: "2026-06-07T00:00:00+00:00"),
    )


def test_planner_input_builder_builds_canonical_request() -> None:
    planning_context = PlanningContext(
        session_id="builder-session",
        task_id="builder-task",
        active_proposals=[],
        active_recommendations=[],
        available_tools=[],
        recent_events=[],
        diagnostics_summary=PlanningDiagnosticsSummary(
            proposal_count=0,
            recommendation_count=0,
            available_tool_count=1,
            event_count=0,
            governance_status="ok",
            has_critical=False,
        ),
    )
    cognitive_state = CognitiveState(
        session_id="builder-session",
        task_id="builder-task",
        active_recommendation_count=0,
        promoted_recommendation_count=0,
        dismissed_recommendation_count=0,
        active_proposal_count=0,
        decision_record_count=0,
        decision_evidence_count=0,
        available_tool_count=1,
        cognitive_health="healthy",
    )
    cognition = FakeCognitiveState(cognitive_state)
    builder = PlannerInputBuilderService(
        sessions=FakeSessions(),
        planning_context=FakePlanningContext(planning_context),
        cognitive_state=cognition,
        tools=FakeTools([builder_tool_record()]),
    )

    request = builder.build("builder-session", "Inspect state")

    assert isinstance(request, PlannerRequest)
    assert request.task_id == "builder-task"
    assert request.objective == "Inspect state"
    assert request.available_tools[0].name == "shell.read"
    assert request.context["context_source"] == "planning_context"
    assert request.context["planning_context"]["session_id"] == "builder-session"
    assert request.cognitive_state == cognitive_state
    assert cognition.received_context == planning_context


def test_planner_request_remains_backward_compatible() -> None:
    request = PlannerRequest(
        task_id="task-1",
        session_id="session-1",
        objective="Direct request",
        available_tools=[],
        context={"source": "direct"},
    )

    assert request.cognitive_state is None


def test_mock_planner_behavior_is_unchanged_with_cognitive_state() -> None:
    request = PlannerRequest(
        task_id="task-1",
        session_id="session-1",
        objective="Choose first enabled",
        available_tools=[
            Tool(
                id="disabled",
                name="shell.write",
                description="Disabled",
                enabled=False,
                created_at="2026-06-07T00:00:00+00:00",
                updated_at="2026-06-07T00:00:00+00:00",
                parameters=[],
            ),
            Tool(
                id="enabled",
                name="shell.read",
                description="Enabled",
                enabled=True,
                created_at="2026-06-07T00:00:00+00:00",
                updated_at="2026-06-07T00:00:00+00:00",
                parameters=[],
            ),
        ],
        cognitive_state=CognitiveState(
            session_id="session-1",
            task_id="task-1",
            active_recommendation_count=0,
            promoted_recommendation_count=0,
            dismissed_recommendation_count=0,
            active_proposal_count=0,
            decision_record_count=0,
            decision_evidence_count=0,
            available_tool_count=1,
            cognitive_health="healthy",
        ),
    )

    response = asyncio.run(MockPlannerAdapter().plan(request))

    assert response.proposed_tool is not None
    assert response.proposed_tool.id == "enabled"


@pytest.mark.parametrize(
    "path",
    [
        "planner-preview",
        "planner-proposal-preview",
        "planner-recommendations",
    ],
)
def test_session_planner_endpoints_use_input_builder(
    monkeypatch,
    path: str,
) -> None:
    client = TestClient(app)
    session = runtime_session_service.create_session(f"task-{path}")
    tool_registry_service.register_tool(
        name=f"shell.read.{path}",
        description="Read files",
    )
    original_build = runtime_routes.planner_input_builder_service.build
    calls: list[tuple[str, str]] = []

    def build(session_id: str, objective: str):
        calls.append((session_id, objective))
        return original_build(session_id, objective)

    monkeypatch.setattr(
        runtime_routes.planner_input_builder_service,
        "build",
        build,
    )

    response = client.post(
        f"/runtime/sessions/{session.id}/{path}",
        json={"objective": "Use canonical input", "context": {"legacy": True}},
    )

    assert response.status_code == 200
    assert calls == [(session.id, "Use canonical input")]
