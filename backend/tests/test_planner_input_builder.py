import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.cognitive_state import CognitiveState
from app.models.planner import PlannerRequest, PlannerResponse
from app.models.planning_context import (
    PlanningContext,
    PlanningDiagnosticsSummary,
)
from app.models.tool import Tool
from app.planner.mock import MockPlannerAdapter
from app.routes import runtime as runtime_routes
from app.services.cognitive_state_service import cognitive_state_service
from app.services.event_service import EventService, event_service
from app.services.planner_input_builder_service import PlannerInputBuilderService
from app.services.planner_recommendation_service import planner_recommendation_service
from app.services.planning_context_service import planning_context_service
from app.services.runtime_session_service import runtime_session_service
from app.services.tool_registry_service import tool_registry_service
from app.services.trace_service import TraceService


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


class RecordingPlanningContext:
    def __init__(self) -> None:
        self.instances: list[PlanningContext] = []

    def build(self, session_id: str) -> PlanningContext:
        planning_context = planning_context_service.build(session_id)
        self.instances.append(planning_context)
        return planning_context


class RecordingCognitiveState:
    def __init__(self) -> None:
        self.instances: list[CognitiveState] = []

    def build(
        self,
        session_id: str,
        planning_context: PlanningContext | None = None,
    ) -> CognitiveState:
        cognitive_state = cognitive_state_service.build(
            session_id,
            planning_context=planning_context,
        )
        self.instances.append(cognitive_state)
        return cognitive_state


def builder_tool_record():
    return SimpleNamespace(
        id="builder-tool",
        name="shell.read",
        description="Read files",
        enabled=True,
        created_at=SimpleNamespace(isoformat=lambda: "2026-06-07T00:00:00+00:00"),
        updated_at=SimpleNamespace(isoformat=lambda: "2026-06-07T00:00:00+00:00"),
    )


def test_planner_input_builder_builds_canonical_request(tmp_path) -> None:
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
        events=EventService(TraceService(tmp_path / "builder-events.db")),
    )

    request = asyncio.run(builder.build("builder-session", "Inspect state"))

    assert isinstance(request, PlannerRequest)
    assert request.task_id == "builder-task"
    assert request.objective == "Inspect state"
    assert request.available_tools[0].name == "shell.read"
    assert request.context["context_source"] == "planning_context"
    assert request.context["planning_context"]["session_id"] == "builder-session"
    assert request.cognitive_state == cognitive_state
    assert request.snapshot_metadata is not None
    assert request.snapshot_metadata.session_id == "builder-session"
    assert request.snapshot_metadata.planner_context_snapshot_version == 1
    assert request.snapshot_metadata.cognitive_state_snapshot_version is None
    assert request.snapshot_metadata.source == "planner_input_builder"
    assert cognition.received_context == planning_context


def test_planner_input_builder_emits_safe_diagnostic_summary(tmp_path) -> None:
    planning_context = PlanningContext(
        session_id="diagnostic-session",
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
        session_id="diagnostic-session",
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
    events = EventService(TraceService(tmp_path / "diagnostic-events.db"))
    builder = PlannerInputBuilderService(
        sessions=FakeSessions(),
        planning_context=FakePlanningContext(planning_context),
        cognitive_state=FakeCognitiveState(cognitive_state),
        tools=FakeTools([builder_tool_record()]),
        events=events,
        clock=lambda: datetime(2026, 6, 7, 12, 0, tzinfo=UTC),
    )

    asyncio.run(builder.build("diagnostic-session", "Inspect diagnostics"))

    emitted = events.list_persisted_events(event_type="planner_input_built")
    assert len(emitted) == 1
    assert emitted[0].metadata == {
        "session_id": "diagnostic-session",
        "planner_context_snapshot_version": 1,
        "built_at": "2026-06-07T12:00:00Z",
        "source": "planner_input_builder",
        "available_recommendation_count": 0,
        "available_tool_count": 1,
    }
    assert "planning_context" not in emitted[0].metadata
    assert "cognitive_state" not in emitted[0].metadata


def test_planner_input_rebuild_is_deterministic_and_non_mutating() -> None:
    session = runtime_session_service.create_session("deterministic-task")
    tool_registry_service.register_tool(
        name="shell.read.deterministic",
        description="Read deterministic state",
    )
    planner_recommendation_service.create_recommendation(
        PlannerRequest(
            task_id=session.task_id,
            session_id=session.id,
            objective="Existing canonical recommendation",
            available_tools=[],
        ),
        PlannerResponse(
            proposed_tool=None,
            rationale="Stable recommendation",
            confidence=0.5,
        ),
        {"governance_status": "ok"},
    )
    recorded_contexts = RecordingPlanningContext()
    recorded_cognition = RecordingCognitiveState()
    build_times = iter(
        [
            datetime(2026, 6, 7, 12, 0, tzinfo=UTC),
            datetime(2026, 6, 7, 12, 1, tzinfo=UTC),
        ]
    )
    builder = PlannerInputBuilderService(
        sessions=runtime_session_service,
        planning_context=recorded_contexts,
        cognitive_state=recorded_cognition,
        tools=tool_registry_service,
        events=event_service,
        clock=lambda: next(build_times),
    )
    session_before = runtime_session_service.get_session(session.id)

    async def build_twice() -> tuple[PlannerRequest, PlannerRequest]:
        first = await builder.build(session.id, "Rebuild canonical input")
        second = await builder.build(session.id, "Rebuild canonical input")
        return first, second

    first, second = asyncio.run(build_twice())
    session_after = runtime_session_service.get_session(session.id)

    first_context = first.context["planning_context"]
    second_context = second.context["planning_context"]
    assert first.session_id == second.session_id == session.id
    assert first.available_tools == second.available_tools
    assert [tool.name for tool in first.available_tools] == [
        "shell.read.deterministic"
    ]
    assert (
        first_context["active_recommendations"]
        == second_context["active_recommendations"]
    )
    assert len(first_context["active_recommendations"]) == 1
    assert first_context == second_context
    assert first.cognitive_state == second.cognitive_state
    assert first.snapshot_metadata is not None
    assert second.snapshot_metadata is not None
    assert first.snapshot_metadata is not second.snapshot_metadata
    assert first.snapshot_metadata.session_id == second.snapshot_metadata.session_id
    assert (
        first.snapshot_metadata.planner_context_snapshot_version
        == second.snapshot_metadata.planner_context_snapshot_version
        == 1
    )
    assert (
        first.snapshot_metadata.cognitive_state_snapshot_version
        is second.snapshot_metadata.cognitive_state_snapshot_version
        is None
    )
    assert first.snapshot_metadata.built_at != second.snapshot_metadata.built_at
    assert first.snapshot_metadata.source == second.snapshot_metadata.source
    assert recorded_contexts.instances[0] is not recorded_contexts.instances[1]
    assert recorded_cognition.instances[0] is not recorded_cognition.instances[1]
    assert session_after.id == session_before.id
    assert session_after.task_id == session_before.task_id
    assert session_after.status == session_before.status
    assert session_after.created_at == session_before.created_at
    assert session_after.completed_at == session_before.completed_at

    input_events = event_service.list_persisted_events(
        event_type="planner_input_built"
    )
    assert len(input_events) == 2
    assert {
        event.metadata["planner_context_snapshot_version"]
        for event in input_events
    } == {1}
    assert {
        event.metadata.get("cognitive_state_snapshot_version")
        for event in input_events
    } == {None}
    assert [event.metadata["built_at"] for event in input_events] == [
        "2026-06-07T12:00:00Z",
        "2026-06-07T12:01:00Z",
    ]
    assert all(
        event.type != "planner_input_built"
        for context in recorded_contexts.instances
        for event in context.recent_events
    )


def test_planner_request_remains_backward_compatible() -> None:
    request = PlannerRequest(
        task_id="task-1",
        session_id="session-1",
        objective="Direct request",
        available_tools=[],
        context={"source": "direct"},
    )

    assert request.cognitive_state is None
    assert request.snapshot_metadata is None


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
        "planner-proposal",
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

    async def build(session_id: str, objective: str):
        calls.append((session_id, objective))
        return await original_build(session_id, objective)

    monkeypatch.setattr(
        runtime_routes.planner_input_builder_service,
        "build",
        build,
    )

    response = client.post(
        f"/runtime/sessions/{session.id}/{path}",
        json={"objective": "Use canonical input", "context": {"legacy": True}},
    )
    trace = client.get("/trace")

    assert response.status_code == 200
    assert trace.status_code == 200
    assert calls == [(session.id, "Use canonical input")]
    input_events = [
        event for event in trace.json() if event["type"] == "planner_input_built"
    ]
    assert len(input_events) == 1
    metadata = input_events[0]["metadata"]
    assert metadata["session_id"] == session.id
    assert metadata["planner_context_snapshot_version"] == 1
    assert metadata["available_tool_count"] == 1
    assert metadata["source"] == "planner_input_builder"
    assert "planning_context" not in metadata
    assert "cognitive_state" not in metadata
