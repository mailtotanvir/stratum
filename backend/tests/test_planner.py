import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.planner import PlannerRequest, PlannerResponse
from app.models.runtime_event import EventType
from app.models.tool import Tool
from app.planner.adapter import PlannerAdapter
from app.planner.mock import MockPlannerAdapter
from app.routes import runtime as runtime_routes
from app.services.event_service import EventService, event_service
from app.services.planner_recommendation_service import planner_recommendation_service
from app.services.planner_service import PlannerService
from app.services.proposal_service import proposal_service
from app.services.runtime_session_service import runtime_session_service
from app.services.tool_execution_service import tool_execution_service
from app.services.tool_invocation_service import tool_invocation_service
from app.services.tool_registry_service import tool_registry_service
from app.services.trace_service import TraceService


def tool(tool_id: str, name: str, enabled: bool = True) -> Tool:
    return Tool(
        id=tool_id,
        name=name,
        description=f"{name} description",
        enabled=enabled,
        created_at="2026-06-05T00:00:00+00:00",
        updated_at="2026-06-05T00:00:00+00:00",
        parameters=[],
    )


def planner_payload(available_tools: list[dict] | None = None) -> dict:
    return {
        "task_id": "task-123",
        "session_id": "session-123",
        "objective": "Choose a tool",
        "available_tools": available_tools
        if available_tools is not None
        else [
            tool("tool-1", "shell.read").model_dump(mode="json"),
        ],
        "context": {"source": "test"},
    }


def test_planner_request_validation() -> None:
    request = PlannerRequest(**planner_payload())

    assert request.task_id == "task-123"
    assert request.session_id == "session-123"
    assert request.available_tools[0].name == "shell.read"
    assert request.context == {"source": "test"}

    with pytest.raises(ValueError):
        PlannerRequest(**{**planner_payload(), "task_id": ""})


def test_planner_response_shape() -> None:
    response = PlannerResponse(
        proposed_tool=tool("tool-1", "shell.read"),
        rationale="Selected first enabled tool: shell.read",
        confidence=0.75,
    )

    assert response.model_dump(mode="json") == {
        "proposed_tool": tool("tool-1", "shell.read").model_dump(mode="json"),
        "rationale": "Selected first enabled tool: shell.read",
        "confidence": 0.75,
    }


def test_mock_planner_adapter_returns_first_enabled_tool() -> None:
    async def run_flow() -> None:
        adapter = MockPlannerAdapter()
        request = PlannerRequest(
            **planner_payload(
                [
                    tool("tool-disabled", "shell.write", enabled=False).model_dump(
                        mode="json"
                    ),
                    tool("tool-enabled", "shell.read", enabled=True).model_dump(
                        mode="json"
                    ),
                    tool("tool-later", "artifact.register", enabled=True).model_dump(
                        mode="json"
                    ),
                ]
            )
        )

        response = await adapter.plan(request)

        assert response.proposed_tool is not None
        assert response.proposed_tool.id == "tool-enabled"
        assert response.rationale == "Selected first enabled tool: shell.read"
        assert response.confidence == 0.75

    asyncio.run(run_flow())


def test_mock_planner_adapter_returns_no_tool_when_none_enabled() -> None:
    async def run_flow() -> None:
        adapter = MockPlannerAdapter()
        request = PlannerRequest(
            **planner_payload(
                [
                    tool("tool-disabled", "shell.write", enabled=False).model_dump(
                        mode="json"
                    )
                ]
            )
        )

        response = await adapter.plan(request)

        assert response.proposed_tool is None
        assert response.rationale == "No enabled tools available for planning."
        assert response.confidence == 0.0

    asyncio.run(run_flow())


def test_planner_service_emits_requested_and_completed(tmp_path) -> None:
    async def run_flow() -> None:
        events = EventService(TraceService(tmp_path / "planner.db"))
        service = PlannerService(adapter=MockPlannerAdapter(), events=events)

        response = await service.plan(PlannerRequest(**planner_payload()))
        emitted = await events.list_events()

        assert response.proposed_tool is not None
        assert [event.type for event in emitted] == [
            EventType.PLANNER_REQUESTED,
            EventType.PLANNER_COMPLETED,
        ]
        assert emitted[0].metadata["task_id"] == "task-123"
        assert emitted[1].metadata["proposed_tool_name"] == "shell.read"

    asyncio.run(run_flow())


def test_planner_plan_endpoint_returns_valid_response() -> None:
    client = TestClient(app)

    response = client.post("/planner/plan", json=planner_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["proposed_tool"]["name"] == "shell.read"
    assert body["rationale"] == "Selected first enabled tool: shell.read"
    assert body["confidence"] == 0.75


def test_planner_plan_endpoint_does_not_trigger_runtime_work_loop() -> None:
    client = TestClient(app)

    response = client.post("/planner/plan", json=planner_payload())
    trace_response = client.get("/trace")

    assert response.status_code == 200
    assert trace_response.status_code == 200
    event_types = [event["type"] for event in trace_response.json()]
    assert "planner_requested" in event_types
    assert "planner_completed" in event_types
    assert "work_loop_started" not in event_types
    assert "work_loop_completed" not in event_types
    assert "tool_invocation_requested" not in event_types
    assert "tool_execution_started" not in event_types
    assert "runtime_task_started" not in event_types


class RecordingPlannerAdapter(PlannerAdapter):
    def __init__(self) -> None:
        self.request: PlannerRequest | None = None

    async def plan(self, request: PlannerRequest) -> PlannerResponse:
        self.request = request
        return PlannerResponse(
            proposed_tool=request.available_tools[0]
            if request.available_tools
            else None,
            rationale="recorded planner request",
            confidence=0.5,
        )


def create_runtime_session(task_id: str = "task-123") -> dict:
    session = runtime_session_service.create_session(task_id)
    return {
        "id": session.id,
        "task_id": session.task_id,
    }


def register_registry_tool(name: str, enabled: bool = True) -> dict:
    record = tool_registry_service.register_tool(
        name=name,
        description=f"{name} description",
        enabled=enabled,
    )
    return {
        "id": record.id,
        "name": record.name,
    }


def test_runtime_planner_preview_returns_planner_response() -> None:
    client = TestClient(app)
    session = create_runtime_session()
    register_registry_tool("shell.read")

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-preview",
        json={"objective": "Choose a session tool", "context": {"source": "preview"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["proposed_tool"]["name"] == "shell.read"
    assert body["rationale"] == "Selected first enabled tool: shell.read"
    assert body["confidence"] == 0.75


def test_runtime_planner_preview_uses_session_task_id_and_available_tools(
    monkeypatch,
) -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-from-session")
    register_registry_tool("shell.read")
    register_registry_tool("artifact.register")
    adapter = RecordingPlannerAdapter()
    original_build = runtime_routes.planning_context_service.build
    built_session_ids: list[str] = []

    def build_planning_context(session_id: str):
        built_session_ids.append(session_id)
        return original_build(session_id)

    monkeypatch.setattr(runtime_routes.planner_service, "_adapter", adapter)
    monkeypatch.setattr(
        runtime_routes.planning_context_service,
        "build",
        build_planning_context,
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-preview",
        json={"objective": "Inspect available tools", "context": {"mode": "test"}},
    )

    assert response.status_code == 200
    assert built_session_ids == [session["id"]]
    assert adapter.request is not None
    assert adapter.request.task_id == "task-from-session"
    assert adapter.request.session_id == session["id"]
    assert adapter.request.objective == "Inspect available tools"
    assert adapter.request.context["context_source"] == "planning_context"
    assert adapter.request.cognitive_state is not None
    assert adapter.request.cognitive_state.session_id == session["id"]
    assert adapter.request.cognitive_state.task_id == "task-from-session"
    assert adapter.request.cognitive_state.available_tool_count == 2
    planning_context = adapter.request.context["planning_context"]
    assert planning_context["session_id"] == session["id"]
    assert planning_context["task_id"] == "task-from-session"
    assert {
        tool["name"] for tool in planning_context["available_tools"]
    } == {
        "shell.read",
        "artifact.register",
    }
    assert {tool.name for tool in adapter.request.available_tools} == {
        "shell.read",
        "artifact.register",
    }


def test_runtime_planner_preview_proposes_first_enabled_tool() -> None:
    client = TestClient(app)
    session = create_runtime_session()
    register_registry_tool("shell.write", enabled=False)
    enabled = register_registry_tool("shell.read", enabled=True)

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-preview",
        json={"objective": "Choose an enabled tool", "context": {}},
    )

    assert response.status_code == 200
    assert response.json()["proposed_tool"]["id"] == enabled["id"]
    assert response.json()["proposed_tool"]["name"] == "shell.read"


def test_runtime_planner_preview_emits_planner_events() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-for-events")
    register_registry_tool("shell.read")

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-preview",
        json={"objective": "Emit planner events", "context": {}},
    )
    trace_response = client.get("/trace")

    assert response.status_code == 200
    assert trace_response.status_code == 200
    planner_events = [
        event
        for event in trace_response.json()
        if event["type"] in ["planner_requested", "planner_completed"]
    ]
    assert [event["type"] for event in planner_events] == [
        "planner_requested",
        "planner_completed",
    ]
    assert planner_events[0]["metadata"]["task_id"] == "task-for-events"
    assert planner_events[0]["metadata"]["session_id"] == session["id"]
    assert planner_events[0]["metadata"]["context_source"] == "planning_context"
    assert planner_events[0]["metadata"]["available_tool_count"] == 1
    assert planner_events[0]["metadata"]["active_proposal_count"] == 0
    assert planner_events[0]["metadata"]["active_recommendation_count"] == 0
    assert planner_events[0]["metadata"]["cognitive_health"] == "healthy"
    assert "planning_context" not in planner_events[0]["metadata"]
    assert "cognitive_state" not in planner_events[0]["metadata"]
    assert planner_events[1]["metadata"]["proposed_tool_name"] == "shell.read"


def test_runtime_planner_preview_does_not_create_invocation_or_execute(
    monkeypatch,
) -> None:
    client = TestClient(app)
    session = create_runtime_session()
    register_registry_tool("shell.read")

    async def fail_run_single_step(*args, **kwargs):
        raise AssertionError("planner preview must not run work loop")

    async def fail_execute_invocation(*args, **kwargs):
        raise AssertionError("planner preview must not execute tools")

    async def fail_run_task(*args, **kwargs):
        raise AssertionError("planner preview must not run runtime task")

    monkeypatch.setattr(
        runtime_routes.work_loop_service,
        "run_single_step",
        fail_run_single_step,
    )
    monkeypatch.setattr(
        tool_execution_service,
        "execute_invocation",
        fail_execute_invocation,
    )
    monkeypatch.setattr(
        runtime_routes.python_async_runtime,
        "run_task",
        fail_run_task,
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-preview",
        json={"objective": "Preview only", "context": {}},
    )
    invocations = tool_invocation_service.list_invocations(session_id=session["id"])
    trace_response = client.get("/trace")

    assert response.status_code == 200
    assert invocations == []
    event_types = [event["type"] for event in trace_response.json()]
    assert "planner_requested" in event_types
    assert "planner_completed" in event_types
    assert "work_loop_started" not in event_types
    assert "tool_invocation_requested" not in event_types
    assert "tool_execution_started" not in event_types


def test_runtime_planner_preview_unknown_session_returns_404() -> None:
    client = TestClient(app)
    register_registry_tool("shell.read")

    response = client.post(
        "/runtime/sessions/missing-session/planner-preview",
        json={"objective": "Preview only", "context": {}},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Runtime session not found: missing-session"


def test_runtime_planner_proposal_endpoint_creates_proposal() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-for-proposal")
    register_registry_tool("shell.read")

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-proposal",
        json={
            "objective": "Create governed proposal",
            "context": {"source": "proposal-test"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    proposal = body["proposal"]
    assert proposal["id"]
    assert proposal["task_id"] == "task-for-proposal"
    assert proposal["title"] == "Planner proposal: Create governed proposal"
    assert proposal["status"] == "proposed"
    assert body["planner_response"]["proposed_tool"]["name"] == "shell.read"

    stored = proposal_service.get_proposal(proposal["id"])
    assert stored.id == proposal["id"]
    assert stored.task_id == "task-for-proposal"


def test_runtime_planner_proposal_stores_planner_details() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-with-details")
    tool_record = register_registry_tool("shell.read")

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-proposal",
        json={
            "objective": "Capture planner details",
            "context": {"path": "README.md"},
        },
    )

    assert response.status_code == 200
    proposal = response.json()["proposal"]
    proposal_body = json.loads(proposal["body"])
    assert proposal_body["session_id"] == session["id"]
    assert proposal_body["task_id"] == "task-with-details"
    assert proposal_body["objective"] == "Capture planner details"
    assert proposal_body["context"] == {"path": "README.md"}
    assert proposal_body["proposed_tool"]["id"] == tool_record["id"]
    assert proposal_body["proposed_tool"]["name"] == "shell.read"
    assert proposal_body["planner_rationale"] == (
        "Selected first enabled tool: shell.read"
    )
    assert proposal_body["planner_confidence"] == 0.75


def test_runtime_planner_proposal_emits_planner_and_bridge_events() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-for-bridge-events")
    register_registry_tool("shell.read")

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-proposal",
        json={"objective": "Emit bridge events", "context": {}},
    )
    trace_response = client.get("/trace")

    assert response.status_code == 200
    proposal_id = response.json()["proposal"]["id"]
    event_types = [event["type"] for event in trace_response.json()]
    assert "planner_requested" in event_types
    assert "planner_completed" in event_types
    assert "proposal_generated" in event_types
    assert "planner_proposal_created" in event_types
    bridge_event = [
        event
        for event in trace_response.json()
        if event["type"] == "planner_proposal_created"
    ][0]
    assert bridge_event["metadata"]["proposal_id"] == proposal_id
    assert bridge_event["metadata"]["session_id"] == session["id"]
    assert bridge_event["metadata"]["task_id"] == "task-for-bridge-events"
    assert bridge_event["metadata"]["proposed_tool_name"] == "shell.read"


def test_runtime_planner_proposal_does_not_create_invocation_or_execute(
    monkeypatch,
) -> None:
    client = TestClient(app)
    session = create_runtime_session()
    register_registry_tool("shell.read")

    async def fail_run_single_step(*args, **kwargs):
        raise AssertionError("planner proposal must not run work loop")

    async def fail_execute_invocation(*args, **kwargs):
        raise AssertionError("planner proposal must not execute tools")

    async def fail_run_task(*args, **kwargs):
        raise AssertionError("planner proposal must not run runtime task")

    monkeypatch.setattr(
        runtime_routes.work_loop_service,
        "run_single_step",
        fail_run_single_step,
    )
    monkeypatch.setattr(
        tool_execution_service,
        "execute_invocation",
        fail_execute_invocation,
    )
    monkeypatch.setattr(
        runtime_routes.python_async_runtime,
        "run_task",
        fail_run_task,
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-proposal",
        json={"objective": "Proposal only", "context": {}},
    )
    invocations = tool_invocation_service.list_invocations(session_id=session["id"])
    trace_response = client.get("/trace")

    assert response.status_code == 200
    assert invocations == []
    event_types = [event["type"] for event in trace_response.json()]
    assert "planner_proposal_created" in event_types
    assert "work_loop_started" not in event_types
    assert "tool_invocation_requested" not in event_types
    assert "tool_execution_started" not in event_types


def test_runtime_planner_proposal_unknown_session_returns_404() -> None:
    client = TestClient(app)
    register_registry_tool("shell.read")

    response = client.post(
        "/runtime/sessions/missing-session/planner-proposal",
        json={"objective": "Proposal only", "context": {}},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Runtime session not found: missing-session"


def test_runtime_planner_proposal_preview_returns_planner_and_governance() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-preview-decision")
    enabled = register_registry_tool("shell.read")

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-proposal-preview",
        json={"objective": "Preview proposal decision", "context": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["planner_response"]["proposed_tool"]["id"] == enabled["id"]
    assert body["planner_response"]["rationale"] == (
        "Selected first enabled tool: shell.read"
    )
    assert body["governance_preview"] == {
        "decision": "allow",
        "reasons": ["within_governance_policy"],
        "governance_status": "ok",
        "error_budget_status": "within_budget",
        "has_critical": False,
    }
    assert body["proposal_allowed"] is True


def test_runtime_planner_proposal_preview_uses_planning_context_service(
    monkeypatch,
) -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-proposal-preview-context")
    register_registry_tool("shell.read")
    proposal_service.create_proposal(
        "Existing proposal",
        "Derived planner input",
        task_id=session["task_id"],
    )
    adapter = RecordingPlannerAdapter()
    original_build = runtime_routes.planning_context_service.build
    built_session_ids: list[str] = []

    def build_planning_context(session_id: str):
        built_session_ids.append(session_id)
        return original_build(session_id)

    monkeypatch.setattr(runtime_routes.planner_service, "_adapter", adapter)
    monkeypatch.setattr(
        runtime_routes.planning_context_service,
        "build",
        build_planning_context,
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-proposal-preview",
        json={
            "objective": "Use derived proposal context",
            "context": {"ignored": True},
        },
    )

    assert response.status_code == 200
    assert built_session_ids == [session["id"]]
    assert adapter.request is not None
    assert adapter.request.objective == "Use derived proposal context"
    planning_context = adapter.request.context["planning_context"]
    assert planning_context["active_proposals"][0]["title"] == (
        "Existing proposal"
    )
    assert adapter.request.available_tools == [
        Tool.model_validate(planning_context["available_tools"][0])
    ]


def test_runtime_planner_proposal_preview_invokes_governance(monkeypatch) -> None:
    client = TestClient(app)
    session = create_runtime_session()
    register_registry_tool("shell.read")
    called = {"count": 0}

    def preview_decision() -> dict:
        called["count"] += 1
        return {
            "decision": "warn",
            "reasons": ["governance_degraded"],
            "governance_status": "degraded",
            "error_budget_status": "within_budget",
            "has_critical": False,
        }

    monkeypatch.setattr(
        runtime_routes.governance_service,
        "preview_decision",
        preview_decision,
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-proposal-preview",
        json={"objective": "Invoke governance", "context": {}},
    )

    assert response.status_code == 200
    assert called["count"] == 1
    assert response.json()["governance_preview"]["decision"] == "warn"
    assert response.json()["proposal_allowed"] is True


def test_runtime_planner_proposal_preview_represents_blocked_governance() -> None:
    client = TestClient(app)
    session = create_runtime_session()
    register_registry_tool("shell.read")
    client.post(
        "/demo/event",
        json={
            "type": "error",
            "severity": "critical",
            "message": "Critical failure",
            "metadata": {"source": "planner_proposal_preview_test"},
        },
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-proposal-preview",
        json={"objective": "Blocked preview", "context": {}},
    )

    assert response.status_code == 200
    assert response.json()["governance_preview"]["decision"] == "block"
    assert response.json()["governance_preview"]["governance_status"] == "critical"
    assert response.json()["proposal_allowed"] is False


def test_runtime_planner_proposal_preview_does_not_create_proposal_or_invocation(
    monkeypatch,
) -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-non-mutating-preview")
    register_registry_tool("shell.read")

    async def fail_run_single_step(*args, **kwargs):
        raise AssertionError("planner proposal preview must not run work loop")

    async def fail_execute_invocation(*args, **kwargs):
        raise AssertionError("planner proposal preview must not execute tools")

    async def fail_run_task(*args, **kwargs):
        raise AssertionError("planner proposal preview must not run runtime task")

    monkeypatch.setattr(
        runtime_routes.work_loop_service,
        "run_single_step",
        fail_run_single_step,
    )
    monkeypatch.setattr(
        tool_execution_service,
        "execute_invocation",
        fail_execute_invocation,
    )
    monkeypatch.setattr(
        runtime_routes.python_async_runtime,
        "run_task",
        fail_run_task,
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-proposal-preview",
        json={"objective": "Do not mutate", "context": {}},
    )
    proposals = proposal_service.list_proposals(task_id="task-non-mutating-preview")
    invocations = tool_invocation_service.list_invocations(session_id=session["id"])
    trace_response = client.get("/trace")

    assert response.status_code == 200
    assert proposals == []
    assert invocations == []
    event_types = [event["type"] for event in trace_response.json()]
    assert "planner_requested" in event_types
    assert "planner_completed" in event_types
    assert "proposal_generated" not in event_types
    assert "planner_proposal_created" not in event_types
    assert "work_loop_started" not in event_types
    assert "tool_invocation_requested" not in event_types
    assert "tool_execution_started" not in event_types


def test_runtime_planner_proposal_preview_unknown_session_returns_404() -> None:
    client = TestClient(app)
    register_registry_tool("shell.read")

    response = client.post(
        "/runtime/sessions/missing-session/planner-proposal-preview",
        json={"objective": "Preview only", "context": {}},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Runtime session not found: missing-session"


def test_runtime_planner_proposal_preview_uses_mock_planner_without_provider_calls() -> None:
    client = TestClient(app)
    session = create_runtime_session()
    register_registry_tool("shell.read")

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-proposal-preview",
        json={"objective": "No provider preview", "context": {}},
    )

    assert isinstance(runtime_routes.planner_service._adapter, MockPlannerAdapter)
    assert response.status_code == 200
    assert response.json()["planner_response"]["confidence"] == 0.75


def test_runtime_planner_proposal_uses_mock_planner_without_provider_calls() -> None:
    client = TestClient(app)
    session = create_runtime_session()
    register_registry_tool("shell.read")

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-proposal",
        json={"objective": "No provider", "context": {}},
    )

    assert isinstance(runtime_routes.planner_service._adapter, MockPlannerAdapter)
    assert response.status_code == 200
    assert response.json()["planner_response"]["confidence"] == 0.75


def test_runtime_planner_recommendation_endpoint_persists_recommendation() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-for-recommendation")
    tool_record = register_registry_tool("shell.read")
    for index in range(25):
        event_service.emit_event_sync(
            EventType.WARNING,
            f"Planning event {index}",
            metadata={"task_id": "task-for-recommendation"},
        )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations",
        json={
            "objective": "Persist recommendation",
            "context": {"source": "recommendation-test"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    recommendation = body["recommendation"]
    assert recommendation["id"]
    assert recommendation["task_id"] == "task-for-recommendation"
    assert recommendation["session_id"] == session["id"]
    assert recommendation["objective"] == "Persist recommendation"
    assert recommendation["proposed_tool"]["id"] == tool_record["id"]
    assert recommendation["proposed_tool"]["name"] == "shell.read"
    assert recommendation["rationale"] == "Selected first enabled tool: shell.read"
    assert recommendation["confidence"] == 0.75
    assert recommendation["governance_status"] == "ok"
    assert recommendation["status"] == "active"
    context_snapshot = recommendation["context_snapshot"]
    assert set(context_snapshot) == {
        "schema_version",
        "active_proposal_count",
        "active_recommendation_count",
        "available_tool_count",
        "recent_event_count",
        "diagnostics_summary",
    }
    assert context_snapshot["schema_version"] == 1
    assert context_snapshot["active_proposal_count"] == 0
    assert context_snapshot["active_recommendation_count"] == 0
    assert context_snapshot["available_tool_count"] == 1
    assert context_snapshot["recent_event_count"] == 20
    assert context_snapshot["diagnostics_summary"]["event_count"] == 20
    assert "recent_events" not in context_snapshot
    assert "active_proposals" not in context_snapshot
    assert body["planner_response"]["proposed_tool"]["name"] == "shell.read"
    assert body["governance_preview"]["decision"] == "allow"

    stored = planner_recommendation_service.get_recommendation(
        recommendation["id"]
    )
    assert stored.id == recommendation["id"]
    assert stored.task_id == "task-for-recommendation"
    assert stored.session_id == session["id"]
    assert (
        planner_recommendation_service.context_snapshot_for(stored)
        == context_snapshot
    )


def test_runtime_planner_recommendation_uses_planning_context_service(
    monkeypatch,
) -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-recommendation-context")
    register_registry_tool("shell.read")
    proposal_service.create_proposal(
        "Existing proposal",
        "Derived recommendation input",
        task_id=session["task_id"],
    )
    adapter = RecordingPlannerAdapter()
    original_build = runtime_routes.planning_context_service.build
    built_session_ids: list[str] = []

    def build_planning_context(session_id: str):
        built_session_ids.append(session_id)
        return original_build(session_id)

    monkeypatch.setattr(runtime_routes.planner_service, "_adapter", adapter)
    monkeypatch.setattr(
        runtime_routes.planning_context_service,
        "build",
        build_planning_context,
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations",
        json={
            "objective": "Use derived recommendation context",
            "context": {"ignored": True},
        },
    )

    assert response.status_code == 200
    assert built_session_ids == [session["id"]]
    assert adapter.request is not None
    assert adapter.request.objective == "Use derived recommendation context"
    assert adapter.request.cognitive_state is not None
    assert adapter.request.cognitive_state.active_proposal_count == 1
    planning_context = adapter.request.context["planning_context"]
    assert planning_context["active_proposals"][0]["title"] == (
        "Existing proposal"
    )
    assert adapter.request.available_tools == [
        Tool.model_validate(planning_context["available_tools"][0])
    ]


def test_runtime_planner_recommendation_event_is_emitted() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-recommendation-events")
    register_registry_tool("shell.read")

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations",
        json={"objective": "Emit recommendation event", "context": {}},
    )
    trace_response = client.get("/trace")

    assert response.status_code == 200
    recommendation_id = response.json()["recommendation"]["id"]
    event_types = [event["type"] for event in trace_response.json()]
    assert "planner_requested" in event_types
    assert "planner_completed" in event_types
    assert "planner_recommendation_created" in event_types
    event = [
        event
        for event in trace_response.json()
        if event["type"] == "planner_recommendation_created"
    ][0]
    assert event["metadata"]["recommendation_id"] == recommendation_id
    assert event["metadata"]["task_id"] == "task-recommendation-events"
    assert event["metadata"]["session_id"] == session["id"]
    assert event["metadata"]["proposed_tool"]["name"] == "shell.read"
    assert event["metadata"]["governance_status"] == "ok"


def test_runtime_planner_recommendations_list_returns_session_records_in_order() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-list-recommendations")
    other_session = create_runtime_session(task_id="other-task")
    register_registry_tool("shell.read")

    first = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations",
        json={"objective": "First recommendation", "context": {}},
    ).json()["recommendation"]
    client.post(
        f"/runtime/sessions/{other_session['id']}/planner-recommendations",
        json={"objective": "Other recommendation", "context": {}},
    )
    second = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations",
        json={"objective": "Second recommendation", "context": {}},
    ).json()["recommendation"]

    response = client.get(
        f"/runtime/sessions/{session['id']}/planner-recommendations"
    )

    assert response.status_code == 200
    assert [record["id"] for record in response.json()] == [
        first["id"],
        second["id"],
    ]
    assert [record["objective"] for record in response.json()] == [
        "First recommendation",
        "Second recommendation",
    ]
    assert all(record["status"] == "active" for record in response.json())


def test_runtime_planner_recommendations_list_filters_by_status() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-filter-recommendations")
    register_registry_tool("shell.read")
    active = create_planner_recommendation(client, session["id"], "Active")
    dismissed = create_planner_recommendation(client, session["id"], "Dismissed")
    dismiss_response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations/"
        f"{dismissed['id']}/dismiss"
    )

    response = client.get(
        f"/runtime/sessions/{session['id']}/planner-recommendations",
        params={"status": "active"},
    )

    assert dismiss_response.status_code == 200
    assert [item["id"] for item in response.json()] == [active["id"]]


def test_runtime_planner_recommendation_does_not_create_proposal_or_execute(
    monkeypatch,
) -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-recommendation-only")
    register_registry_tool("shell.read")

    async def fail_run_single_step(*args, **kwargs):
        raise AssertionError("planner recommendation must not run work loop")

    async def fail_execute_invocation(*args, **kwargs):
        raise AssertionError("planner recommendation must not execute tools")

    async def fail_run_task(*args, **kwargs):
        raise AssertionError("planner recommendation must not run runtime task")

    monkeypatch.setattr(
        runtime_routes.work_loop_service,
        "run_single_step",
        fail_run_single_step,
    )
    monkeypatch.setattr(
        tool_execution_service,
        "execute_invocation",
        fail_execute_invocation,
    )
    monkeypatch.setattr(
        runtime_routes.python_async_runtime,
        "run_task",
        fail_run_task,
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations",
        json={"objective": "Recommend only", "context": {}},
    )
    proposals = proposal_service.list_proposals(task_id="task-recommendation-only")
    invocations = tool_invocation_service.list_invocations(session_id=session["id"])
    trace_response = client.get("/trace")

    assert response.status_code == 200
    assert proposals == []
    assert invocations == []
    event_types = [event["type"] for event in trace_response.json()]
    assert "planner_recommendation_created" in event_types
    assert "proposal_generated" not in event_types
    assert "planner_proposal_created" not in event_types
    assert "work_loop_started" not in event_types
    assert "tool_invocation_requested" not in event_types
    assert "tool_execution_started" not in event_types


def test_runtime_planner_recommendation_unknown_session_returns_404() -> None:
    client = TestClient(app)
    register_registry_tool("shell.read")

    post_response = client.post(
        "/runtime/sessions/missing-session/planner-recommendations",
        json={"objective": "Recommend only", "context": {}},
    )
    get_response = client.get(
        "/runtime/sessions/missing-session/planner-recommendations"
    )

    assert post_response.status_code == 404
    assert get_response.status_code == 404
    assert post_response.json()["detail"] == (
        "Runtime session not found: missing-session"
    )
    assert get_response.json()["detail"] == (
        "Runtime session not found: missing-session"
    )


def test_runtime_planner_recommendation_uses_mock_planner_without_provider_calls() -> None:
    client = TestClient(app)
    session = create_runtime_session()
    register_registry_tool("shell.read")

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations",
        json={"objective": "No provider recommendation", "context": {}},
    )

    assert isinstance(runtime_routes.planner_service._adapter, MockPlannerAdapter)
    assert response.status_code == 200
    assert response.json()["planner_response"]["confidence"] == 0.75


def create_planner_recommendation(
    client: TestClient,
    session_id: str,
    objective: str = "Recommendation to promote",
) -> dict:
    response = client.post(
        f"/runtime/sessions/{session_id}/planner-recommendations",
        json={"objective": objective, "context": {}},
    )
    assert response.status_code == 200
    return response.json()["recommendation"]


def test_runtime_planner_recommendation_can_be_promoted_to_proposal() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-promote-recommendation")
    register_registry_tool("shell.read")
    recommendation = create_planner_recommendation(client, session["id"])

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations/"
        f"{recommendation['id']}/promote"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["recommendation"]["id"] == recommendation["id"]
    assert body["recommendation"]["status"] == "promoted"
    proposal = body["proposal"]
    assert proposal["id"]
    assert proposal["task_id"] == "task-promote-recommendation"
    assert proposal["title"] == (
        "Planner recommendation proposal: Recommendation to promote"
    )
    assert proposal["status"] == "proposed"
    assert proposal["source_type"] == "planner_recommendation"
    assert proposal["source_id"] == recommendation["id"]
    assert proposal["source_context_snapshot"] == recommendation["context_snapshot"]
    assert proposal["source_context_snapshot"]["schema_version"] == 1

    stored = proposal_service.get_proposal(proposal["id"])
    assert stored.id == proposal["id"]
    assert stored.task_id == "task-promote-recommendation"
    assert stored.source_type == "planner_recommendation"
    assert stored.source_id == recommendation["id"]
    assert (
        proposal_service.source_context_snapshot_for(stored)
        == recommendation["context_snapshot"]
    )
    assert (
        planner_recommendation_service.get_recommendation(
            recommendation["id"]
        ).status
        == "promoted"
    )


def test_promote_legacy_recommendation_without_context_snapshot() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-legacy-promotion")
    register_registry_tool("shell.read")
    available_tool = runtime_routes.to_available_tool(
        tool_registry_service.get_tool_by_name("shell.read")
    )
    recommendation = planner_recommendation_service.create_recommendation(
        PlannerRequest(
            task_id=session["task_id"],
            session_id=session["id"],
            objective="Promote legacy recommendation",
            available_tools=[available_tool],
            context={},
        ),
        PlannerResponse(
            proposed_tool=available_tool,
            rationale="Legacy recommendation",
            confidence=0.5,
        ),
        {"governance_status": "ok"},
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations/"
        f"{recommendation.id}/promote"
    )

    assert response.status_code == 200
    proposal = response.json()["proposal"]
    assert proposal["source_type"] == "planner_recommendation"
    assert proposal["source_id"] == recommendation.id
    assert proposal["source_context_snapshot"] is None


def test_promoted_proposal_contains_recommendation_details() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-promoted-details")
    tool_record = register_registry_tool("shell.read")
    recommendation = create_planner_recommendation(
        client,
        session["id"],
        objective="Capture promoted details",
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations/"
        f"{recommendation['id']}/promote"
    )

    assert response.status_code == 200
    proposal_body = json.loads(response.json()["proposal"]["body"])
    assert proposal_body == {
        "session_id": session["id"],
        "task_id": "task-promoted-details",
        "objective": "Capture promoted details",
        "proposed_tool": {
            "id": tool_record["id"],
            "name": "shell.read",
            "description": "shell.read description",
            "enabled": True,
            "created_at": recommendation["proposed_tool"]["created_at"],
            "updated_at": recommendation["proposed_tool"]["updated_at"],
            "parameters": [],
        },
        "planner_rationale": "Selected first enabled tool: shell.read",
        "planner_confidence": 0.75,
        "governance_status": "ok",
        "source_recommendation_id": recommendation["id"],
    }


def test_promote_recommendation_session_mismatch_is_rejected() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-owner")
    other_session = create_runtime_session(task_id="task-other")
    register_registry_tool("shell.read")
    recommendation = create_planner_recommendation(client, session["id"])

    response = client.post(
        f"/runtime/sessions/{other_session['id']}/planner-recommendations/"
        f"{recommendation['id']}/promote"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Planner recommendation does not belong to runtime session: "
        f"{recommendation['id']}"
    )


def test_dismiss_recommendation_sets_status_without_execution(monkeypatch) -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-dismiss-recommendation")
    register_registry_tool("shell.read")
    recommendation = create_planner_recommendation(client, session["id"])

    async def fail_async(*args, **kwargs):
        raise AssertionError("dismissal must remain advisory")

    monkeypatch.setattr(runtime_routes.planner_service, "plan", fail_async)
    monkeypatch.setattr(
        runtime_routes.work_loop_service,
        "run_single_step",
        fail_async,
    )
    monkeypatch.setattr(
        tool_execution_service,
        "execute_invocation",
        fail_async,
    )
    monkeypatch.setattr(
        runtime_routes.python_async_runtime,
        "run_task",
        fail_async,
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations/"
        f"{recommendation['id']}/dismiss"
    )
    proposals = proposal_service.list_proposals(task_id=session["task_id"])
    invocations = tool_invocation_service.list_invocations(session_id=session["id"])
    events = client.get("/trace").json()

    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"
    assert proposals == []
    assert invocations == []
    assert any(
        event["type"] == "planner_recommendation_dismissed"
        and event["metadata"]["status"] == "dismissed"
        for event in events
    )
    event_types = [event["type"] for event in events]
    assert "work_loop_started" not in event_types
    assert "tool_invocation_requested" not in event_types
    assert "tool_execution_started" not in event_types


def test_dismissed_recommendation_cannot_be_promoted() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-dismissed-terminal")
    register_registry_tool("shell.read")
    recommendation = create_planner_recommendation(client, session["id"])
    client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations/"
        f"{recommendation['id']}/dismiss"
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations/"
        f"{recommendation['id']}/promote"
    )

    assert response.status_code == 409
    assert proposal_service.list_proposals(task_id=session["task_id"]) == []


def test_promoted_recommendation_cannot_be_dismissed() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-promoted-terminal")
    register_registry_tool("shell.read")
    recommendation = create_planner_recommendation(client, session["id"])
    client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations/"
        f"{recommendation['id']}/promote"
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations/"
        f"{recommendation['id']}/dismiss"
    )

    assert response.status_code == 409


def test_promote_missing_recommendation_returns_404() -> None:
    client = TestClient(app)
    session = create_runtime_session()

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations/"
        "missing-recommendation/promote"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Planner recommendation not found: missing-recommendation"
    )


def test_promote_recommendation_emits_event() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-promote-event")
    register_registry_tool("shell.read")
    recommendation = create_planner_recommendation(client, session["id"])

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations/"
        f"{recommendation['id']}/promote"
    )
    trace_response = client.get("/trace")

    assert response.status_code == 200
    proposal_id = response.json()["proposal"]["id"]
    event = [
        event
        for event in trace_response.json()
        if event["type"] == "planner_recommendation_promoted"
    ][0]
    proposal_event = [
        event
        for event in trace_response.json()
        if event["type"] == "proposal_generated"
        and event["metadata"]["proposal_id"] == proposal_id
    ][0]
    assert event["metadata"]["recommendation_id"] == recommendation["id"]
    assert event["metadata"]["proposal_id"] == proposal_id
    assert event["metadata"]["task_id"] == "task-promote-event"
    assert event["metadata"]["session_id"] == session["id"]
    assert event["metadata"]["proposed_tool"]["name"] == "shell.read"
    assert event["metadata"]["has_source_context_snapshot"] is True
    assert proposal_event["metadata"]["source_type"] == "planner_recommendation"
    assert proposal_event["metadata"]["source_id"] == recommendation["id"]
    assert proposal_event["metadata"]["has_source_context_snapshot"] is True
    assert (
        proposal_event["metadata"]["source_context_snapshot"]
        == recommendation["context_snapshot"]
    )


def test_promote_recommendation_does_not_create_invocation_or_execute(
    monkeypatch,
) -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-promote-only")
    register_registry_tool("shell.read")
    recommendation = create_planner_recommendation(client, session["id"])

    async def fail_run_single_step(*args, **kwargs):
        raise AssertionError("recommendation promotion must not run work loop")

    async def fail_execute_invocation(*args, **kwargs):
        raise AssertionError("recommendation promotion must not execute tools")

    async def fail_run_task(*args, **kwargs):
        raise AssertionError("recommendation promotion must not run runtime task")

    monkeypatch.setattr(
        runtime_routes.work_loop_service,
        "run_single_step",
        fail_run_single_step,
    )
    monkeypatch.setattr(
        tool_execution_service,
        "execute_invocation",
        fail_execute_invocation,
    )
    monkeypatch.setattr(
        runtime_routes.python_async_runtime,
        "run_task",
        fail_run_task,
    )

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations/"
        f"{recommendation['id']}/promote"
    )
    invocations = tool_invocation_service.list_invocations(session_id=session["id"])
    trace_response = client.get("/trace")

    assert response.status_code == 200
    assert invocations == []
    event_types = [event["type"] for event in trace_response.json()]
    assert "planner_recommendation_promoted" in event_types
    assert "work_loop_started" not in event_types
    assert "tool_invocation_requested" not in event_types
    assert "tool_execution_started" not in event_types


def test_promote_recommendation_allows_duplicate_promotions() -> None:
    client = TestClient(app)
    session = create_runtime_session(task_id="task-duplicate-promotion")
    register_registry_tool("shell.read")
    recommendation = create_planner_recommendation(client, session["id"])

    first = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations/"
        f"{recommendation['id']}/promote"
    )
    second = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations/"
        f"{recommendation['id']}/promote"
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["proposal"]["id"] != second.json()["proposal"]["id"]
    assert second.json()["recommendation"]["status"] == "promoted"


def test_promote_recommendation_uses_persisted_record_without_provider_calls() -> None:
    client = TestClient(app)
    session = create_runtime_session()
    register_registry_tool("shell.read")
    recommendation = create_planner_recommendation(client, session["id"])

    response = client.post(
        f"/runtime/sessions/{session['id']}/planner-recommendations/"
        f"{recommendation['id']}/promote"
    )

    assert isinstance(runtime_routes.planner_service._adapter, MockPlannerAdapter)
    assert response.status_code == 200
    assert response.json()["recommendation"]["id"] == recommendation["id"]
