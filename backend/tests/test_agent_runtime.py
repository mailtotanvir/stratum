import inspect

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType, Severity
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.python_async_runtime import PythonAsyncRuntime
from app.services.event_service import EventService
from app.services.governance_service import GovernanceService
from app.services.interrupt_service import InterruptService, interrupt_service
from app.services.runtime_execution_service import (
    RuntimeExecutionNotFoundError,
    RuntimeExecutionService,
)
from app.services.runtime_session_service import RuntimeSessionService
from app.services.stop_service import StopService, stop_service
from app.services.trace_service import TraceService


@pytest.fixture
def events(tmp_path) -> EventService:
    return EventService(TraceService(tmp_path / "runtime.db"))


@pytest.fixture
def executions(tmp_path) -> RuntimeExecutionService:
    return RuntimeExecutionService(tmp_path / "runtime_executions.db")


@pytest.fixture
def interrupts(tmp_path) -> InterruptService:
    return InterruptService(tmp_path / "interrupts.db")


@pytest.fixture
def stops(tmp_path) -> StopService:
    return StopService(tmp_path / "stops.db")


@pytest.fixture
def sessions(tmp_path) -> RuntimeSessionService:
    return RuntimeSessionService(tmp_path / "runtime_sessions.db")


def test_python_async_runtime_preserves_agent_runtime_shape(events) -> None:
    runtime = PythonAsyncRuntime(events=events)

    assert isinstance(runtime, AgentRuntime)
    assert inspect.iscoroutinefunction(runtime.run_task)
    assert inspect.iscoroutinefunction(runtime.interrupt)
    assert inspect.iscoroutinefunction(runtime.stop)
    assert inspect.signature(AgentRuntime.run_task).return_annotation is dict
    assert inspect.signature(AgentRuntime.interrupt).return_annotation is dict
    assert inspect.signature(AgentRuntime.stop).return_annotation is dict


@pytest.mark.anyio
async def test_runtime_run_emits_event(events, executions, sessions) -> None:
    runtime = PythonAsyncRuntime(
        events=events,
        executions=executions,
        sessions=sessions,
    )

    response = await runtime.run_task("task-123")
    emitted = await events.list_events()

    assert response == {
        "task_id": "task-123",
        "status": "started",
        "governance": {
            "decision": "allow",
            "reasons": ["within_governance_policy"],
        },
    }

    event = emitted[-1]
    assert event.type == EventType.RUNTIME_TASK_STARTED
    assert event.severity == Severity.INFO
    assert event.metadata == {
        "task_id": "task-123",
        "runtime": "python_async",
    }

    assert [event.type for event in emitted] == [
        EventType.RUNTIME_SESSION_CREATED,
        EventType.RUNTIME_SESSION_RUNNING,
        EventType.RUNTIME_TASK_STARTED,
    ]


@pytest.mark.anyio
async def test_governance_allow_starts_runtime_execution(events, executions) -> None:
    runtime = PythonAsyncRuntime(
        events=events,
        executions=executions,
        governance=GovernanceService(events),
    )

    response = await runtime.run_task("task-123")
    execution = executions.get("task-123")

    assert response == {
        "task_id": "task-123",
        "status": "started",
        "governance": {
            "decision": "allow",
            "reasons": ["within_governance_policy"],
        },
    }
    assert execution.state == "running"


@pytest.mark.anyio
async def test_governance_warn_emits_warning_and_still_starts(
    events,
    executions,
) -> None:
    await events.emit_event(
        EventType.WARNING,
        "Pre-existing warning",
        severity=Severity.WARNING,
        metadata={"source": "test"},
    )
    runtime = PythonAsyncRuntime(
        events=events,
        executions=executions,
        governance=GovernanceService(events),
    )

    response = await runtime.run_task("task-123")
    execution = executions.get("task-123")
    emitted = await events.list_events()

    assert response == {
        "task_id": "task-123",
        "status": "started",
        "governance": {
            "decision": "warn",
            "reasons": ["governance_degraded"],
        },
    }
    assert execution.state == "running"
    assert EventType.RUNTIME_GOVERNANCE_WARNING in [
        event.type
        for event in emitted
    ]
    assert [event.type for event in emitted[-3:]] == [
        EventType.RUNTIME_SESSION_CREATED,
        EventType.RUNTIME_SESSION_RUNNING,
        EventType.RUNTIME_TASK_STARTED,
    ]
    warning = next(
        event
        for event in emitted
        if event.type == EventType.RUNTIME_GOVERNANCE_WARNING
    )
    assert warning.metadata == {
        "task_id": "task-123",
        "decision": "warn",
        "reasons": ["governance_degraded"],
    }


@pytest.mark.anyio
async def test_governance_block_emits_blocked_and_does_not_start(
    events,
    executions,
) -> None:
    await events.emit_event(
        EventType.ERROR,
        "Critical failure",
        severity=Severity.CRITICAL,
        metadata={"source": "test"},
    )
    runtime = PythonAsyncRuntime(
        events=events,
        executions=executions,
        governance=GovernanceService(events),
    )

    response = await runtime.run_task("task-123")
    emitted = await events.list_events()

    assert response == {
        "task_id": "task-123",
        "status": "blocked",
        "governance": {
            "decision": "block",
            "reasons": ["critical_event_present", "error_budget_exhausted"],
        },
    }
    assert emitted[-1].type == EventType.RUNTIME_GOVERNANCE_BLOCKED
    assert emitted[-1].metadata == {
        "task_id": "task-123",
        "decision": "block",
        "reasons": ["critical_event_present", "error_budget_exhausted"],
    }
    with pytest.raises(RuntimeExecutionNotFoundError):
        executions.get("task-123")


@pytest.mark.anyio
async def test_blocked_run_does_not_create_running_runtime_execution_record(
    events,
    executions,
) -> None:
    await events.emit_event(
        EventType.ERROR,
        "Critical failure",
        severity=Severity.CRITICAL,
        metadata={"source": "test"},
    )
    runtime = PythonAsyncRuntime(
        events=events,
        executions=executions,
        governance=GovernanceService(events),
    )

    await runtime.run_task("task-123")

    assert executions.list() == []


@pytest.mark.anyio
async def test_runtime_interrupt_emits_event(events, executions, interrupts) -> None:
    runtime = PythonAsyncRuntime(
        events=events,
        executions=executions,
        interrupts=interrupts,
    )

    response = await runtime.interrupt("task-123", "operator requested pause")
    emitted = await events.list_events()

    assert response["interrupt_request_id"]
    assert response == {
        "runtime": "python_async",
        "task_id": "task-123",
        "status": "interrupted",
        "reason": "operator requested pause",
        "interrupt_request_id": response["interrupt_request_id"],
    }

    event = emitted[-1]
    assert event.type == EventType.RUNTIME_TASK_INTERRUPTED
    assert event.severity == Severity.WARNING
    assert event.metadata == {
        "task_id": "task-123",
        "runtime": "python_async",
        "reason": "operator requested pause",
    }

    assert [event.type for event in emitted] == [
        EventType.INTERRUPT_REQUESTED,
        EventType.INTERRUPT_APPLIED,
        EventType.RUNTIME_TASK_INTERRUPTED,
    ]


@pytest.mark.anyio
async def test_runtime_stop_emits_event(events, executions, stops) -> None:
    runtime = PythonAsyncRuntime(
        events=events,
        executions=executions,
        stops=stops,
    )

    response = await runtime.stop("task-123", "operator requested stop")
    emitted = await events.list_events()

    assert response["stop_request_id"]
    assert response == {
        "runtime": "python_async",
        "task_id": "task-123",
        "status": "stopped",
        "reason": "operator requested stop",
        "stop_request_id": response["stop_request_id"],
    }

    event = emitted[-1]
    assert event.type == EventType.RUNTIME_TASK_STOPPED
    assert event.severity == Severity.WARNING
    assert event.metadata == {
        "task_id": "task-123",
        "runtime": "python_async",
        "reason": "operator requested stop",
    }

    assert [event.type for event in emitted] == [
        EventType.STOP_REQUESTED,
        EventType.STOP_APPLIED,
        EventType.RUNTIME_TASK_STOPPED,
    ]


@pytest.mark.anyio
async def test_start_creates_runtime_state(events, executions) -> None:
    runtime = PythonAsyncRuntime(events=events, executions=executions)

    await runtime.run_task("task-123")
    execution = executions.get("task-123")

    assert execution.task_id == "task-123"
    assert execution.state == "running"
    assert execution.started_at is not None
    assert execution.interrupted_at is None
    assert execution.stopped_at is None
    assert execution.updated_at is not None


@pytest.mark.anyio
async def test_interrupt_transitions_runtime_state(events, executions) -> None:
    runtime = PythonAsyncRuntime(events=events, executions=executions)

    await runtime.run_task("task-123")
    await runtime.interrupt("task-123", "operator requested pause")
    execution = executions.get("task-123")

    assert execution.state == "interrupted"
    assert execution.started_at is not None
    assert execution.interrupted_at is not None
    assert execution.stopped_at is None


@pytest.mark.anyio
async def test_stop_transitions_runtime_state(events, executions) -> None:
    runtime = PythonAsyncRuntime(events=events, executions=executions)

    await runtime.run_task("task-123")
    await runtime.stop("task-123", "operator requested stop")
    execution = executions.get("task-123")

    assert execution.state == "stopped"
    assert execution.started_at is not None
    assert execution.interrupted_at is None
    assert execution.stopped_at is not None


def test_runtime_state_survives_reconstruction_from_persistence(tmp_path) -> None:
    db_path = tmp_path / "runtime_executions.db"
    service = RuntimeExecutionService(db_path)
    service.start("task-123")
    service.interrupt("task-123")

    reconstructed = RuntimeExecutionService(db_path)
    execution = reconstructed.get("task-123")

    assert execution.task_id == "task-123"
    assert execution.state == "interrupted"
    assert execution.started_at is not None
    assert execution.interrupted_at is not None
    assert execution.stopped_at is None


def test_runtime_events_appear_in_trace_filtered_by_task_id() -> None:
    client = TestClient(app)

    run_response = client.post("/runtime/tasks/task-123/run")
    interrupt_response = client.post(
        "/runtime/tasks/task-456/interrupt",
        json={"reason": "operator requested pause"},
    )
    stop_response = client.post(
        "/runtime/tasks/task-123/stop",
        json={"reason": "operator requested stop"},
    )
    trace_response = client.get("/trace", params={"task_id": "task-123"})

    assert run_response.status_code == 200
    assert interrupt_response.status_code == 200
    assert stop_response.status_code == 200
    assert trace_response.status_code == 200

    events = trace_response.json()
    assert [event["type"] for event in events] == [
        "runtime_session_created",
        "runtime_session_running",
        "runtime_task_started",
        "stop_requested",
        "stop_applied",
        "runtime_session_stopped",
        "runtime_task_stopped",
    ]
    assert [event["metadata"]["task_id"] for event in events] == [
        "task-123",
        "task-123",
        "task-123",
        "task-123",
        "task-123",
        "task-123",
        "task-123",
    ]


def test_governance_events_appear_in_trace_filtered_by_task_id() -> None:
    client = TestClient(app)

    client.post(
        "/demo/event",
        json={
            "type": "warning",
            "severity": "warning",
            "message": "Pre-existing warning",
            "metadata": {"source": "test"},
        },
    )
    run_response = client.post("/runtime/tasks/task-123/run")
    trace_response = client.get("/trace", params={"task_id": "task-123"})

    assert run_response.status_code == 200
    assert trace_response.status_code == 200
    events = trace_response.json()
    assert [event["type"] for event in events] == [
        "reflection_requested",
        "runtime_governance_warning",
        "runtime_session_created",
        "runtime_session_running",
        "runtime_task_started",
    ]
    assert events[0]["metadata"]["task_id"] == "task-123"
    assert events[0]["metadata"]["status"] == "pending"
    assert events[0]["metadata"]["reasons"] == [
        "governance_degraded",
        "decision_preview_not_allow",
    ]
    assert events[1]["metadata"] == {
        "task_id": "task-123",
        "decision": "warn",
        "reasons": ["governance_degraded"],
    }


def test_runtime_endpoints_return_deterministic_responses() -> None:
    client = TestClient(app)

    run_response = client.post("/runtime/tasks/task-123/run")
    interrupt_response = client.post(
        "/runtime/tasks/task-123/interrupt",
        json={"reason": "operator requested pause"},
    )
    stop_response = client.post(
        "/runtime/tasks/task-123/stop",
        json={"reason": "operator requested stop"},
    )

    assert run_response.status_code == 200
    assert run_response.json() == {
        "task_id": "task-123",
        "status": "started",
        "governance": {
            "decision": "allow",
            "reasons": ["within_governance_policy"],
        },
    }

    assert interrupt_response.status_code == 200
    assert interrupt_response.json() == {
        "runtime": "python_async",
        "task_id": "task-123",
        "status": "interrupted",
        "reason": "operator requested pause",
        "interrupt_request_id": interrupt_response.json()["interrupt_request_id"],
    }

    assert stop_response.status_code == 200
    assert stop_response.json() == {
        "runtime": "python_async",
        "task_id": "task-123",
        "status": "stopped",
        "reason": "operator requested stop",
        "stop_request_id": stop_response.json()["stop_request_id"],
    }


def test_runtime_run_endpoint_returns_deterministic_governance_payload() -> None:
    client = TestClient(app)

    response = client.post("/runtime/tasks/task-123/run")

    assert response.status_code == 200
    assert response.json() == {
        "task_id": "task-123",
        "status": "started",
        "governance": {
            "decision": "allow",
            "reasons": ["within_governance_policy"],
        },
    }


def test_runtime_get_endpoint_returns_tracked_execution() -> None:
    client = TestClient(app)

    run_response = client.post("/runtime/tasks/task-123/run")
    get_response = client.get("/runtime/tasks/task-123")

    assert run_response.status_code == 200
    assert get_response.status_code == 200
    assert get_response.json()["task_id"] == "task-123"
    assert get_response.json()["state"] == "running"
    assert get_response.json()["started_at"] is not None
    assert get_response.json()["interrupted_at"] is None
    assert get_response.json()["stopped_at"] is None
    assert get_response.json()["updated_at"] is not None


def test_runtime_list_endpoint_returns_tracked_runtime_executions() -> None:
    client = TestClient(app)

    first = client.post("/runtime/tasks/task-123/run")
    second = client.post(
        "/runtime/tasks/task-456/stop",
        json={"reason": "operator requested stop"},
    )
    list_response = client.get("/runtime/tasks")

    assert first.status_code == 200
    assert second.status_code == 200
    assert list_response.status_code == 200

    executions_by_task_id = {
        execution["task_id"]: execution
        for execution in list_response.json()
    }
    assert executions_by_task_id["task-123"]["state"] == "running"
    assert executions_by_task_id["task-456"]["state"] == "stopped"


def test_warning_run_creates_pending_reflection_request() -> None:
    client = TestClient(app)

    client.post(
        "/demo/event",
        json={
            "type": "warning",
            "severity": "warning",
            "message": "Pre-existing warning",
            "metadata": {"source": "test"},
        },
    )
    run_response = client.post("/runtime/tasks/task-123/run")
    reflections_response = client.get("/reflections", params={"task_id": "task-123"})

    assert run_response.status_code == 200
    assert reflections_response.status_code == 200
    requests = reflections_response.json()
    assert len(requests) == 1
    assert requests[0]["task_id"] == "task-123"
    assert requests[0]["status"] == "pending"
    assert requests[0]["reasons"] == [
        "governance_degraded",
        "decision_preview_not_allow",
    ]
    assert requests[0]["resolved_at"] is None


def test_blocked_run_creates_pending_reflection_request() -> None:
    client = TestClient(app)

    client.post(
        "/demo/event",
        json={
            "type": "error",
            "severity": "critical",
            "message": "Critical failure",
            "metadata": {"source": "test"},
        },
    )
    run_response = client.post("/runtime/tasks/task-123/run")
    reflections_response = client.get("/reflections", params={"task_id": "task-123"})

    assert run_response.status_code == 200
    assert run_response.json()["status"] == "blocked"
    requests = reflections_response.json()
    assert len(requests) == 1
    assert requests[0]["task_id"] == "task-123"
    assert requests[0]["status"] == "pending"
    assert requests[0]["reasons"] == [
        "governance_critical",
        "error_budget_exhausted",
        "decision_preview_not_allow",
    ]


def test_allow_run_does_not_create_reflection_request() -> None:
    client = TestClient(app)

    run_response = client.post("/runtime/tasks/task-123/run")
    reflections_response = client.get("/reflections", params={"task_id": "task-123"})

    assert run_response.status_code == 200
    assert run_response.json()["status"] == "started"
    assert reflections_response.status_code == 200
    assert reflections_response.json() == []


def test_list_reflections_by_status() -> None:
    client = TestClient(app)

    client.post(
        "/demo/event",
        json={
            "type": "warning",
            "severity": "warning",
            "message": "Pre-existing warning",
            "metadata": {"source": "test"},
        },
    )
    client.post("/runtime/tasks/task-123/run")
    pending = client.get("/reflections", params={"status": "pending"}).json()
    request_id = pending[0]["id"]

    resolve_response = client.post(f"/reflections/{request_id}/resolve")
    resolved_response = client.get("/reflections", params={"status": "resolved"})
    pending_response = client.get("/reflections", params={"status": "pending"})

    assert resolve_response.status_code == 200
    assert resolved_response.status_code == 200
    assert pending_response.status_code == 200
    assert [request["id"] for request in resolved_response.json()] == [request_id]
    assert pending_response.json() == []


def test_list_reflections_by_task_id() -> None:
    client = TestClient(app)

    client.post(
        "/demo/event",
        json={
            "type": "warning",
            "severity": "warning",
            "message": "Pre-existing warning",
            "metadata": {"source": "test"},
        },
    )
    first = client.post("/runtime/tasks/task-123/run")
    second = client.post("/runtime/tasks/task-456/run")
    response = client.get("/reflections", params={"task_id": "task-123"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert response.status_code == 200
    requests = response.json()
    assert len(requests) == 1
    assert requests[0]["task_id"] == "task-123"


def test_resolve_reflection_transitions_to_resolved() -> None:
    client = TestClient(app)

    client.post(
        "/demo/event",
        json={
            "type": "warning",
            "severity": "warning",
            "message": "Pre-existing warning",
            "metadata": {"source": "test"},
        },
    )
    client.post("/runtime/tasks/task-123/run")
    request_id = client.get("/reflections").json()[0]["id"]

    resolve_response = client.post(f"/reflections/{request_id}/resolve")
    get_response = client.get(f"/reflections/{request_id}")

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "resolved"
    assert resolve_response.json()["resolved_at"] is not None
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "resolved"


def test_double_resolve_reflection_returns_409() -> None:
    client = TestClient(app)

    client.post(
        "/demo/event",
        json={
            "type": "warning",
            "severity": "warning",
            "message": "Pre-existing warning",
            "metadata": {"source": "test"},
        },
    )
    client.post("/runtime/tasks/task-123/run")
    request_id = client.get("/reflections").json()[0]["id"]

    first = client.post(f"/reflections/{request_id}/resolve")
    second = client.post(f"/reflections/{request_id}/resolve")

    assert first.status_code == 200
    assert second.status_code == 409


def test_reflection_events_appear_in_trace_filtered_by_task_id() -> None:
    client = TestClient(app)

    client.post(
        "/demo/event",
        json={
            "type": "warning",
            "severity": "warning",
            "message": "Pre-existing warning",
            "metadata": {"source": "test"},
        },
    )
    client.post("/runtime/tasks/task-123/run")
    request_id = client.get("/reflections", params={"task_id": "task-123"}).json()[0][
        "id"
    ]
    client.post(f"/reflections/{request_id}/resolve")
    trace_response = client.get("/trace", params={"task_id": "task-123"})

    assert trace_response.status_code == 200
    event_types = [event["type"] for event in trace_response.json()]
    assert "reflection_requested" in event_types
    assert "reflection_resolved" in event_types


def test_interrupt_creates_persisted_interrupt_request() -> None:
    client = TestClient(app)

    response = client.post(
        "/runtime/tasks/task-123/interrupt",
        json={"reason": "operator requested pause"},
    )
    request_id = response.json()["interrupt_request_id"]
    get_response = client.get(f"/interrupts/{request_id}")

    assert response.status_code == 200
    assert get_response.status_code == 200
    assert get_response.json()["id"] == request_id
    assert get_response.json()["task_id"] == "task-123"
    assert get_response.json()["reason"] == "operator requested pause"


def test_interrupt_applies_request_immediately() -> None:
    client = TestClient(app)

    response = client.post(
        "/runtime/tasks/task-123/interrupt",
        json={"reason": "operator requested pause"},
    )
    request_id = response.json()["interrupt_request_id"]
    get_response = client.get(f"/interrupts/{request_id}")

    assert response.status_code == 200
    assert get_response.json()["status"] == "applied"
    assert get_response.json()["resolved_at"] is not None


def test_interrupt_runtime_state_becomes_interrupted() -> None:
    client = TestClient(app)

    interrupt_response = client.post(
        "/runtime/tasks/task-123/interrupt",
        json={"reason": "operator requested pause"},
    )
    runtime_response = client.get("/runtime/tasks/task-123")

    assert interrupt_response.status_code == 200
    assert runtime_response.status_code == 200
    assert runtime_response.json()["state"] == "interrupted"


def test_interrupt_events_appear_in_trace_filtered_by_task_id() -> None:
    client = TestClient(app)

    response = client.post(
        "/runtime/tasks/task-123/interrupt",
        json={"reason": "operator requested pause"},
    )
    trace_response = client.get("/trace", params={"task_id": "task-123"})

    assert response.status_code == 200
    assert trace_response.status_code == 200
    assert [event["type"] for event in trace_response.json()] == [
        "interrupt_requested",
        "interrupt_applied",
        "runtime_task_interrupted",
    ]


def test_list_interrupts_by_status() -> None:
    client = TestClient(app)
    pending = interrupt_service.create_request(
        task_id="task-123",
        reason="operator requested pause",
    )
    client.post(
        "/runtime/tasks/task-456/interrupt",
        json={"reason": "operator requested pause"},
    )

    requested_response = client.get("/interrupts", params={"status": "requested"})
    applied_response = client.get("/interrupts", params={"status": "applied"})

    assert requested_response.status_code == 200
    assert applied_response.status_code == 200
    assert [request["id"] for request in requested_response.json()] == [pending.id]
    assert [request["status"] for request in applied_response.json()] == ["applied"]


def test_list_interrupts_by_task_id() -> None:
    client = TestClient(app)

    first = client.post(
        "/runtime/tasks/task-123/interrupt",
        json={"reason": "operator requested pause"},
    )
    second = client.post(
        "/runtime/tasks/task-456/interrupt",
        json={"reason": "operator requested pause"},
    )
    response = client.get("/interrupts", params={"task_id": "task-123"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert response.status_code == 200
    requests = response.json()
    assert len(requests) == 1
    assert requests[0]["task_id"] == "task-123"


def test_ignore_pending_interrupt_request_works() -> None:
    client = TestClient(app)
    pending = interrupt_service.create_request(
        task_id="task-123",
        reason="operator requested pause",
    )

    response = client.post(f"/interrupts/{pending.id}/ignore")
    get_response = client.get(f"/interrupts/{pending.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert response.json()["resolved_at"] is not None
    assert get_response.json()["status"] == "ignored"


def test_applying_already_applied_or_ignored_interrupt_returns_409() -> None:
    client = TestClient(app)
    applied = interrupt_service.create_request(
        task_id="task-123",
        reason="operator requested pause",
    )
    ignored = interrupt_service.create_request(
        task_id="task-456",
        reason="operator requested pause",
    )
    interrupt_service.apply_request(applied.id)
    interrupt_service.ignore_request(ignored.id)

    applied_response = client.post(f"/interrupts/{applied.id}/apply")
    ignored_response = client.post(f"/interrupts/{ignored.id}/apply")

    assert applied_response.status_code == 409
    assert ignored_response.status_code == 409


def test_stop_creates_persisted_stop_request() -> None:
    client = TestClient(app)

    response = client.post(
        "/runtime/tasks/task-123/stop",
        json={"reason": "operator requested stop"},
    )
    request_id = response.json()["stop_request_id"]
    get_response = client.get(f"/stops/{request_id}")

    assert response.status_code == 200
    assert get_response.status_code == 200
    assert get_response.json()["id"] == request_id
    assert get_response.json()["task_id"] == "task-123"
    assert get_response.json()["reason"] == "operator requested stop"


def test_stop_applies_request_immediately() -> None:
    client = TestClient(app)

    response = client.post(
        "/runtime/tasks/task-123/stop",
        json={"reason": "operator requested stop"},
    )
    request_id = response.json()["stop_request_id"]
    get_response = client.get(f"/stops/{request_id}")

    assert response.status_code == 200
    assert get_response.json()["status"] == "applied"
    assert get_response.json()["resolved_at"] is not None


def test_stop_runtime_state_becomes_stopped() -> None:
    client = TestClient(app)

    stop_response = client.post(
        "/runtime/tasks/task-123/stop",
        json={"reason": "operator requested stop"},
    )
    runtime_response = client.get("/runtime/tasks/task-123")

    assert stop_response.status_code == 200
    assert runtime_response.status_code == 200
    assert runtime_response.json()["state"] == "stopped"


def test_stop_events_appear_in_trace_filtered_by_task_id() -> None:
    client = TestClient(app)

    response = client.post(
        "/runtime/tasks/task-123/stop",
        json={"reason": "operator requested stop"},
    )
    trace_response = client.get("/trace", params={"task_id": "task-123"})

    assert response.status_code == 200
    assert trace_response.status_code == 200
    assert [event["type"] for event in trace_response.json()] == [
        "stop_requested",
        "stop_applied",
        "runtime_task_stopped",
    ]


def test_list_stops_by_status() -> None:
    client = TestClient(app)
    pending = stop_service.create_request(
        task_id="task-123",
        reason="operator requested stop",
    )
    client.post(
        "/runtime/tasks/task-456/stop",
        json={"reason": "operator requested stop"},
    )

    requested_response = client.get("/stops", params={"status": "requested"})
    applied_response = client.get("/stops", params={"status": "applied"})

    assert requested_response.status_code == 200
    assert applied_response.status_code == 200
    assert [request["id"] for request in requested_response.json()] == [pending.id]
    assert [request["status"] for request in applied_response.json()] == ["applied"]


def test_list_stops_by_task_id() -> None:
    client = TestClient(app)

    first = client.post(
        "/runtime/tasks/task-123/stop",
        json={"reason": "operator requested stop"},
    )
    second = client.post(
        "/runtime/tasks/task-456/stop",
        json={"reason": "operator requested stop"},
    )
    response = client.get("/stops", params={"task_id": "task-123"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert response.status_code == 200
    requests = response.json()
    assert len(requests) == 1
    assert requests[0]["task_id"] == "task-123"


def test_ignore_pending_stop_request_works() -> None:
    client = TestClient(app)
    pending = stop_service.create_request(
        task_id="task-123",
        reason="operator requested stop",
    )

    response = client.post(f"/stops/{pending.id}/ignore")
    get_response = client.get(f"/stops/{pending.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert response.json()["resolved_at"] is not None
    assert get_response.json()["status"] == "ignored"


def test_applying_already_applied_or_ignored_stop_returns_409() -> None:
    client = TestClient(app)
    applied = stop_service.create_request(
        task_id="task-123",
        reason="operator requested stop",
    )
    ignored = stop_service.create_request(
        task_id="task-456",
        reason="operator requested stop",
    )
    stop_service.apply_request(applied.id)
    stop_service.ignore_request(ignored.id)

    applied_response = client.post(f"/stops/{applied.id}/apply")
    ignored_response = client.post(f"/stops/{ignored.id}/apply")

    assert applied_response.status_code == 409
    assert ignored_response.status_code == 409
