"""Thin FastAPI transport adapter.

FastAPI is a transport, not the runtime. This module exposes the exact same
engine the CLI drives over HTTP. The runtime works without it; remove this
file and nothing in the core changes.

NOTE: this module deliberately avoids `from __future__ import annotations`.
Postponed evaluation turns parameter annotations into strings that FastAPI
cannot resolve for closure-local request models, silently degrading them to
query parameters.
"""

from dataclasses import dataclass
from typing import Any, Callable

from .approval import ApprovalRecord
from .engine import ExecutionSnapshot
from .errors import InvalidTransitionError, StratumError
from .replay import fold


@dataclass
class RuntimeHolder:
    """Single runtime instance shared by all requests."""

    runtime: Any
    read_events: Callable[[str], list]
    list_executions: Callable[[], list] | None = None


def create_app(holder: RuntimeHolder):
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
    except ImportError as exc:  # pragma: no cover
        raise StratumError(
            "the API adapter requires fastapi: pip install 'stratum[api]'"
        ) from exc

    app = FastAPI(title="Stratum", version="0.1")

    class CreateTaskBody(BaseModel):
        repo_path: str
        task_description: str
        selected_files: list[str] | None = None
        markdown_context: str = ""

    class DecisionBody(BaseModel):
        decider: str = "api-operator"

    def _snapshot_or_404(execution_id: str) -> ExecutionSnapshot:
        try:
            return holder.runtime.execution(execution_id)
        except InvalidTransitionError:
            raise HTTPException(status_code=404, detail="unknown execution") from None

    def _pending_plan_id(execution_id: str) -> str:
        snapshot = _snapshot_or_404(execution_id)
        if snapshot.plan is None:
            raise HTTPException(
                status_code=409, detail="no pending plan for this execution"
            )
        return snapshot.plan.id

    @app.post("/tasks")
    async def create_task(body: CreateTaskBody) -> dict[str, Any]:
        snapshot = await holder.runtime.start_planning(
            repo_path=body.repo_path,
            task_description=body.task_description,
            selected_files=body.selected_files,
            markdown_context=body.markdown_context,
        )
        return _serialize(snapshot)

    @app.get("/tasks/{execution_id}")
    async def get_task(execution_id: str) -> dict[str, Any]:
        return _serialize(_snapshot_or_404(execution_id))

    @app.post("/tasks/{execution_id}/approve")
    async def approve_task(
        execution_id: str, body: DecisionBody
    ) -> dict[str, Any]:
        plan_id = _pending_plan_id(execution_id)
        record = ApprovalRecord("granted", body.decider, plan_id)
        result = await holder.runtime.decide_and_execute(execution_id, record)
        return _serialize(result)

    @app.post("/tasks/{execution_id}/reject")
    async def reject_task(
        execution_id: str, body: DecisionBody
    ) -> dict[str, Any]:
        plan_id = _pending_plan_id(execution_id)
        record = ApprovalRecord("rejected", body.decider, plan_id)
        result = await holder.runtime.decide_and_execute(execution_id, record)
        return _serialize(result)

    @app.get("/tasks/{execution_id}/events")
    async def task_events(execution_id: str) -> list[dict[str, Any]]:
        events = holder.read_events(execution_id)
        if not events:
            raise HTTPException(status_code=404, detail="no recorded events")
        return [e.to_dict() for e in events]

    @app.get("/tasks/{execution_id}/replay")
    async def task_replay(execution_id: str) -> dict[str, Any]:
        events = holder.read_events(execution_id)
        if not events:
            raise HTTPException(status_code=404, detail="no recorded events")
        replayed = fold(events)
        return {
            "status": replayed.status,
            "description": replayed.description,
            "steps": replayed.plan_steps,
            "tool_calls": replayed.tool_calls,
            "artifacts": replayed.artifacts,
            "error": replayed.error,
        }

    return app


def _serialize(snapshot: ExecutionSnapshot) -> dict[str, Any]:
    return {
        "task_id": snapshot.task_id,
        "execution_id": snapshot.execution_id,
        "status": snapshot.status.value,
        "repo_path": snapshot.repo_path,
        "task_description": snapshot.task_description,
        "error": snapshot.error,
        "observations": list(snapshot.observations),
        "plan": snapshot.plan.to_dict() if snapshot.plan else None,
    }
