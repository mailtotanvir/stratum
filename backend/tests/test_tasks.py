import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType
from app.models.task import TaskCreate, TaskStatus
from app.routes.stream import trace
from app.routes import task as task_routes
from app.services.event_service import event_service
from app.services.task_service import TaskNotFoundError, TaskService


def test_task_routes_are_mounted() -> None:
    paths = {route.path for route in app.routes}

    assert "/tasks" in paths
    assert "/tasks/{task_id}" in paths
    assert "/tasks/{task_id}/trace" in paths
    assert "/reconstruct/tasks" in paths
    assert "/reconstruct/tasks/consistency" in paths
    assert "/reconstruct/tasks/{task_id}" in paths
    assert "/reconstruct/tasks/{task_id}/compare" in paths


def test_task_routes_create_get_and_list_newest_first(tmp_path) -> None:
    task_routes.task_service = TaskService(tmp_path / "tasks.db")

    first = task_routes.create_task(TaskCreate(title="First task"))
    second = task_routes.create_task(TaskCreate(title="Second task"))

    assert first.status == TaskStatus.CREATED
    assert first.title == "First task"
    assert task_routes.get_task(first.id) == first
    assert task_routes.get_task(second.id) == second
    assert task_routes.list_tasks() == [second, first]


def test_task_api_endpoints_create_get_and_list_tasks(tmp_path) -> None:
    task_routes.task_service = TaskService(tmp_path / "tasks.db")
    client = TestClient(app)

    created = client.post("/tasks", json={"title": "API task"})

    assert created.status_code == 200
    body = created.json()
    assert body["title"] == "API task"
    assert body["status"] == "created"
    assert body["completed_at"] is None
    assert body["summary"] is None

    assert client.get(f"/tasks/{body['id']}").json() == body
    listed = client.get("/tasks").json()
    assert listed[0] == body


def test_task_trace_returns_only_events_for_requested_task() -> None:
    async def run_flow() -> None:
        first = await event_service.emit_event(
            EventType.TASK_CREATED,
            "First",
            metadata={"task_id": "task-1"},
        )
        await event_service.emit_event(
            EventType.TASK_CREATED,
            "Second",
            metadata={"task_id": "task-2"},
        )
        completed = await event_service.emit_event(
            EventType.TASK_COMPLETED,
            "First completed",
            metadata={"task_id": "task-1"},
        )
        client = TestClient(app)

        response = client.get("/tasks/task-1/trace")

        assert response.status_code == 200
        assert response.json() == [first.to_dict(), completed.to_dict()]

    asyncio.run(run_flow())


def test_task_trace_type_filter_uses_task_id_and_type() -> None:
    async def run_flow() -> None:
        await event_service.emit_event(
            EventType.TASK_COMPLETED,
            "Other completed",
            metadata={"task_id": "task-2"},
        )
        expected = await event_service.emit_event(
            EventType.TASK_COMPLETED,
            "Target completed",
            metadata={"task_id": "task-1"},
        )
        await event_service.emit_event(
            EventType.TASK_RUNNING,
            "Target running",
            metadata={"task_id": "task-1"},
        )
        client = TestClient(app)

        response = client.get(
            "/tasks/task-1/trace",
            params={"type": "task_completed"},
        )

        assert response.status_code == 200
        assert response.json() == [expected.to_dict()]

    asyncio.run(run_flow())


def test_task_trace_limit_returns_recent_matches_in_chronological_order() -> None:
    async def run_flow() -> None:
        await event_service.emit_event(
            EventType.TASK_RUNNING,
            "First running",
            metadata={"task_id": "task-1"},
        )
        second = await event_service.emit_event(
            EventType.TASK_RUNNING,
            "Second running",
            metadata={"task_id": "task-1"},
        )
        third = await event_service.emit_event(
            EventType.TASK_COMPLETED,
            "Third completed",
            metadata={"task_id": "task-1"},
        )
        await event_service.emit_event(
            EventType.TASK_RUNNING,
            "Other running",
            metadata={"task_id": "task-2"},
        )
        client = TestClient(app)

        response = client.get("/tasks/task-1/trace", params={"limit": 2})

        assert response.status_code == 200
        assert response.json() == [second.to_dict(), third.to_dict()]

    asyncio.run(run_flow())


def test_task_trace_unknown_task_id_returns_empty_list() -> None:
    async def run_flow() -> None:
        await event_service.emit_event(
            EventType.TASK_CREATED,
            "Known task",
            metadata={"task_id": "task-1"},
        )
        client = TestClient(app)

        response = client.get("/tasks/unknown/trace")

        assert response.status_code == 200
        assert response.json() == []

    asyncio.run(run_flow())


def test_task_service_persists_tasks_and_lifecycle_statuses(tmp_path) -> None:
    db_path = tmp_path / "tasks.db"
    writer = TaskService(db_path)
    created = writer.create_task("Persisted task")
    running = writer.mark_running(created.id)
    completed = writer.mark_completed(created.id, summary="Done")

    reader = TaskService(db_path)

    assert running.id == created.id
    assert running.status == TaskStatus.RUNNING
    assert completed.status == TaskStatus.COMPLETED
    assert completed.summary == "Done"
    assert completed.completed_at is not None
    assert reader.get_task(created.id).status == TaskStatus.COMPLETED
    assert reader.list_tasks()[0].id == created.id


def test_task_service_failed_status_persists(tmp_path) -> None:
    service = TaskService(tmp_path / "tasks.db")
    created = service.create_task("Failing task")
    failed = service.mark_failed(created.id, summary="No budget")

    assert failed.status == TaskStatus.FAILED
    assert failed.summary == "No budget"
    assert failed.completed_at is not None
    assert service.get_task(created.id).status == TaskStatus.FAILED


def test_task_lifecycle_events_appear_in_trace(tmp_path) -> None:
    service = TaskService(tmp_path / "tasks.db")
    created = service.create_task("Trace task")
    service.mark_running(created.id)
    service.mark_completed(created.id, summary="Traced")

    persisted = trace()

    assert [event["type"] for event in persisted[-3:]] == [
        "task_created",
        "task_running",
        "task_completed",
    ]
    assert [event["metadata"]["task_id"] for event in persisted[-3:]] == [
        created.id,
        created.id,
        created.id,
    ]
    assert persisted[-1]["metadata"]["summary"] == "Traced"


def test_task_service_missing_task_raises(tmp_path) -> None:
    service = TaskService(tmp_path / "tasks.db")

    with pytest.raises(TaskNotFoundError):
        service.get_task("missing")

