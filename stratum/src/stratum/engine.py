"""The Stratum runtime engine.

One coherent lifecycle, causally driven by real actions:

    TASK_CREATED -> PLANNING -> PLAN_READY -> APPROVAL_REQUIRED
        -> APPROVED | REJECTED -> EXECUTING -> OBSERVING
            -> COMPLETED | FAILED | CANCELLED

Invariants enforced structurally in this module:

1. Nothing is observable until something actually happened.
2. Nothing can be approved unless something was actually proposed.
3. Nothing can be proposed unless a real provider interaction produced it.
4. Nothing can be executed unless it passed the approval boundary.
5. Every meaningful transition produces durable events.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .store import SqliteEventStore

from .ai import AIAdapter, AIRequest
from .approval import ApprovalPolicy, ApprovalRecord
from .context import RepoContext, load_repository_context
from .errors import (
    InvalidTransitionError,
    PlanValidationError,
    ProviderError,
    RepositoryError,
    ToolError,
)
from .events import (
    ARTIFACT_CREATED,
    AI_REQUESTED,
    AI_RESPONDED,
    APPROVAL_GRANTED,
    APPROVAL_REJECTED,
    APPROVAL_REQUESTED,
    EXECUTION_STARTED,
    OBSERVATION_RECORDED,
    PLAN_GENERATED,
    TASK_CANCELLED,
    TASK_COMPLETED,
    TASK_CREATED,
    TASK_FAILED,
    TASK_PLANNING_STARTED,
    TOOL_COMPLETED,
    TOOL_FAILED,
    TOOL_STARTED,
    EventFactory,
    RuntimeEvent,
    utc_now_iso,
)
from .ids import execution_id as new_execution_id
from .ids import task_id as new_task_id
from .planning import Planner, Plan, PlanStep, parse_plan
from .publisher import EventPublisher
from .tools import ExecutionContext, default_tool_registry


class ExecutionStatus(str, Enum):
    TASK_CREATED = "TASK_CREATED"
    PLANNING = "PLANNING"
    PLAN_READY = "PLAN_READY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    OBSERVING = "OBSERVING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATUSES = {
    ExecutionStatus.COMPLETED,
    ExecutionStatus.FAILED,
    ExecutionStatus.CANCELLED,
    ExecutionStatus.REJECTED,
}


@dataclass(frozen=True)
class ExecutionSnapshot:
    """Public, immutable view of an execution."""

    task_id: str
    execution_id: str
    repo_path: str
    task_description: str
    status: ExecutionStatus
    plan: Plan | None = None
    observations: tuple[dict[str, Any], ...] = ()
    error: str | None = None


@dataclass
class _State:
    task_id: str
    execution_id: str
    repo_path: Path
    task_description: str
    status: ExecutionStatus = ExecutionStatus.TASK_CREATED
    created_at: str = ""
    context: RepoContext | None = None
    plan: Plan | None = None
    factory: EventFactory | None = None
    scratch: dict[str, Any] = field(default_factory=dict)
    observations: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    decider: str | None = None
    cancel_requested: bool = False
    started_monotonic: float = 0.0


class StratumRuntime:
    """Execution-first runtime orchestrator.

    Pass ``store`` (a SqliteEventStore) to make execution state durable:
    every event is indexed and every lifecycle transition projected, so
    pending approvals survive process restarts (see ``resume_pending``).
    """

    def __init__(
        self,
        *,
        adapter: AIAdapter,
        model: str,
        publisher: EventPublisher,
        approval_policy: ApprovalPolicy,
        planner: Planner | None = None,
        store: "SqliteEventStore | None" = None,
    ) -> None:
        import asyncio

        from .store import AsyncSqliteStore

        self._adapter = adapter
        self._model = model
        self._publisher = publisher
        self._approval_policy = approval_policy
        self._planner = planner or Planner(model=model)
        self.store = store
        self._async_store = AsyncSqliteStore(store) if store else None
        self._states: dict[str, _State] = {}
        self._asyncio = asyncio

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_planning(
        self,
        *,
        repo_path: Path | str,
        task_description: str,
        selected_files: list[str] | None = None,
        markdown_context: str = "",
    ) -> ExecutionSnapshot:
        """Task + repository -> validated structured plan awaiting approval."""
        tid = new_task_id()
        eid = new_execution_id()
        state = _State(
            task_id=tid,
            execution_id=eid,
            repo_path=Path(repo_path).expanduser().resolve(),
            task_description=task_description,
            created_at=_utcnow_iso(),
        )
        state.factory = EventFactory(tid, eid)
        state.status = ExecutionStatus.PLANNING
        self._states[eid] = state
        await self._persist(state)

        try:
            ctx = load_repository_context(
                repo_path=state.repo_path,
                task_description=task_description,
                selected_files=selected_files,
                markdown_context=markdown_context,
            )
        except RepositoryError as exc:
            return await self._fail_immediately(state, str(exc))

        state.context = ctx
        await self._emit(state, TASK_CREATED, {
            "description": task_description,
            "repo_path": str(ctx.root),
            "git": ctx.git.to_dict(),
            "rollback_ref": ctx.git.head,
        })
        await self._emit(state, TASK_PLANNING_STARTED, {})

        state.status = ExecutionStatus.PLAN_READY
        request = self._planner.build_request(ctx)
        await self._emit_ai_requested(state, request, purpose="planning")

        try:
            response = await self._adapter.generate(request)
        except ProviderError as exc:
            return await self._fail_immediately(state, f"provider failed: {exc}")

        await self._emit_ai_responded(state, response, purpose="planning")

        try:
            plan = parse_plan(
                response.content,
                task_id=tid,
                provider=self._adapter.provider_name,
                model=response.model or self._model,
            )
        except PlanValidationError as exc:
            return await self._fail_immediately(state, f"invalid plan: {exc}")

        state.plan = plan
        await self._emit(state, PLAN_GENERATED, {"plan": plan.to_dict()})

        state.status = ExecutionStatus.APPROVAL_REQUIRED
        await self._emit(state, APPROVAL_REQUESTED, {
            "plan_id": plan.id,
            "step_count": len(plan.steps),
            "steps": [
                {"index": s.index, "action_type": s.action_type,
                 "description": s.description}
                for s in plan.steps
            ],
        })
        await self._persist(state)
        return self.snapshot(eid)

    async def decide_and_execute(
        self,
        execution_id: str,
        record: ApprovalRecord | None = None,
    ) -> ExecutionSnapshot:
        """Apply the human decision; execute only when granted."""
        state = self._require_state(execution_id)
        if state.status != ExecutionStatus.APPROVAL_REQUIRED:
            raise InvalidTransitionError(
                f"cannot resolve approval from status {state.status.value}"
            )

        if record is None:
            assert state.plan is not None
            record = self._approval_policy.decide(execution_id, state.plan)

        assert state.plan is not None
        if record.plan_id != state.plan.id:
            raise InvalidTransitionError(
                f"decision references plan {record.plan_id}, "
                f"pending plan is {state.plan.id}"
            )

        if record.decision == "rejected":
            state.status = ExecutionStatus.REJECTED
            state.decider = record.decider
            await self._emit(state, APPROVAL_REJECTED, {
                "plan_id": state.plan.id,
                "decider": record.decider,
            })
            await self._persist(state)
            return self.snapshot(execution_id)

        state.status = ExecutionStatus.APPROVED
        state.decider = record.decider
        await self._emit(state, APPROVAL_GRANTED, {
            "plan_id": state.plan.id,
            "decider": record.decider,
        })
        await self._persist(state)

        return await self._execute(state)

    async def cancel(self, execution_id: str) -> ExecutionSnapshot:
        state = self._require_state(execution_id)
        if state.status in TERMINAL_STATUSES:
            raise InvalidTransitionError(
                f"execution already terminal: {state.status.value}"
            )
        state.cancel_requested = True
        if state.status == ExecutionStatus.APPROVAL_REQUIRED:
            state.status = ExecutionStatus.CANCELLED
            await self._emit(state, TASK_CANCELLED, {"phase": "before_execution"})
            await self._persist(state)
        return self.snapshot(execution_id)

    def execution(self, execution_id: str) -> ExecutionSnapshot:
        return self.snapshot(execution_id)

    # ------------------------------------------------------------------
    # Restart recovery
    # ------------------------------------------------------------------

    async def resume_pending(self) -> list[ExecutionSnapshot]:
        """Hydrate APPROVAL_REQUIRED executions persisted by a previous run.

        After this, decide_and_execute works on them exactly as before the
        restart. Event sequences continue from the last recorded event;
        the correlation id is preserved so replay stays coherent.
        """
        if self.store is None:
            return []
        resumed: list[ExecutionSnapshot] = []
        for record in self.store.pending_executions():
            if record.execution_id in self._states or record.plan is None:
                continue
            repo = Path(record.repo_path)
            from .context import RepoContext, collect_git_info

            state = _State(
                task_id=record.task_id,
                execution_id=record.execution_id,
                repo_path=repo,
                task_description=record.task_description,
                status=ExecutionStatus.APPROVAL_REQUIRED,
                created_at=record.created_at or utc_now_iso(),
                context=RepoContext(root=repo, git=collect_git_info(repo)),
                plan=record.plan,
                factory=EventFactory(
                    record.task_id,
                    record.execution_id,
                    start_sequence=record.last_event_sequence,
                    correlation_id=record.correlation_id,
                ),
                decider=None,
            )
            self._states[record.execution_id] = state
            resumed.append(self.snapshot_from(state))
        return resumed

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _execute(self, state: _State) -> ExecutionSnapshot:
        plan = state.plan
        assert plan is not None
        state.status = ExecutionStatus.EXECUTING
        state.started_monotonic = time.monotonic()
        await self._persist(state)

        tools = default_tool_registry()
        tool_ctx = ExecutionContext(workspace=state.context.root, scratch=state.scratch)

        await self._emit(state, EXECUTION_STARTED, {
            "plan_id": plan.id,
            "step_count": len(plan.steps),
        })

        for step in plan.steps:
            if state.cancel_requested:
                break
            ok = await self._execute_step(state, step, tools, tool_ctx)
            if not ok:
                return self.snapshot(state.execution_id)

        if state.cancel_requested:
            state.status = ExecutionStatus.CANCELLED
            await self._emit(state, TASK_CANCELLED, {"phase": "mid_execution"})
            await self._persist(state)
            return self.snapshot(state.execution_id)

        state.status = ExecutionStatus.OBSERVING
        duration_ms = int((time.monotonic() - state.started_monotonic) * 1000)
        ok_count = sum(1 for o in state.observations if o.get("ok"))
        state.status = ExecutionStatus.COMPLETED
        await self._emit(state, TASK_COMPLETED, {
            "steps_total": len(plan.steps),
            "steps_ok": ok_count,
            "duration_ms": duration_ms,
        })
        await self._persist(state)
        return self.snapshot(state.execution_id)

    async def _execute_step(
        self,
        state: _State,
        step: PlanStep,
        tools: dict[str, Any],
        tool_ctx: ExecutionContext,
    ) -> bool:
        params = await self._build_params(state, step)

        await self._emit(state, TOOL_STARTED, {
            "step_id": step.id,
            "index": step.index,
            "action_type": step.action_type,
            "path": step.path,
            "command": step.command,
        })

        tool = tools.get(step.action_type)
        if tool is None:
            return await self._step_failed(
                state, step, f"no tool registered for {step.action_type!r}")

        try:
            result = await tool.execute(params, tool_ctx)
        except ToolError as exc:
            return await self._step_failed(state, step, str(exc))

        payload = {
            "step_id": step.id,
            "index": step.index,
            "summary": result.summary,
            "duration_ms": result.duration_ms,
        }
        await self._emit(state, TOOL_COMPLETED, payload)

        observation = {
            "index": step.index,
            "action_type": step.action_type,
            "ok": result.ok,
            "summary": result.summary,
            **({"exit_code": result.details["exit_code"]}
               if "exit_code" in result.details else {}),
        }
        state.observations.append(observation)
        await self._emit(state, OBSERVATION_RECORDED, {
            "step_id": step.id,
            **observation,
            "details": _bounded(result.details),
        })

        if step.action_type == "write_file":
            await self._emit(state, ARTIFACT_CREATED, {
                "path": result.details["path"],
                "kind": "file_write",
                "bytes": result.details["bytes"],
                "sha256_after": result.details["after_sha256"],
                "diff": result.details["diff"],
            })

        if not result.ok:
            # A command that ran but exited non-zero fails the execution.
            return await self._task_failed_from_step(
                state, step,
                f"verification failed at step {step.index}: {result.summary}")
        return True

    async def _build_params(self, state: _State, step: PlanStep) -> dict[str, Any]:
        if step.action_type == "read_file":
            return {"path": step.path}

        if step.action_type == "run_command":
            return {"command": step.command}

        if step.action_type == "write_file":
            content = step.content
            if content is None:
                cached_key = f"file:{step.path}"
                current = state.scratch.get(cached_key)
                if current is None and step.path:
                    # Restarted between read and write: ground in reality.
                    candidate = state.context.root / step.path
                    if candidate.is_file():
                        current = candidate.read_text("utf-8", errors="replace")
                new_content, response = await self._materialize_with_events(
                    state, step, current)
                content = new_content
            return {"path": step.path, "content": content}

        raise ToolError(f"unsupported action type: {step.action_type}")

    async def _materialize_with_events(
        self, state: _State, step: PlanStep, current_content: str | None
    ):
        from .materialize import build_materialize_request, extract_content

        path = step.path or "(unknown)"
        request = build_materialize_request(
            step=step,
            task_description=state.task_description,
            path=path,
            current_content=current_content,
        )
        request = AIRequest(
            model=self._model,
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            metadata=request.metadata,
        )
        await self._emit_ai_requested(state, request, purpose="materialize_write")
        response = await self._adapter.generate(request)
        await self._emit_ai_responded(state, response, purpose="materialize_write")
        return extract_content(response.content), response

    async def _step_failed(
        self, state: _State, step: PlanStep, message: str
    ) -> bool:
        await self._emit(state, TOOL_FAILED, {
            "step_id": step.id,
            "index": step.index,
            "error": message,
        })
        state.observations.append({
            "index": step.index,
            "action_type": step.action_type,
            "ok": False,
            "summary": message,
        })
        await self._emit(state, OBSERVATION_RECORDED, {
            "step_id": step.id,
            "index": step.index,
            "action_type": step.action_type,
            "ok": False,
            "summary": message,
        })
        return await self._task_failed_from_step(state, step, message)

    async def _task_failed_from_step(
        self, state: _State, step: PlanStep, message: str
    ) -> bool:
        state.error = message
        state.status = ExecutionStatus.FAILED
        await self._emit(state, TASK_FAILED, {
            "failed_at_step": step.index,
            "error": message,
        })
        await self._persist(state)
        return False

    async def _fail_immediately(self, state: _State, message: str) -> ExecutionSnapshot:
        state.error = message
        state.status = ExecutionStatus.FAILED
        await self._emit(state, TASK_FAILED, {"error": message})
        await self._persist(state)
        del self._states[state.execution_id]
        return self.snapshot_from(state)

    # ------------------------------------------------------------------
    # Event helpers + persistence
    # ------------------------------------------------------------------

    async def _emit(
        self, state: _State, event_type: str, payload: dict[str, Any]
    ) -> RuntimeEvent:
        assert state.factory is not None
        event = state.factory.emit(event_type, payload)
        await self._publisher.publish(event)
        if self._async_store is not None:
            await self._async_store.append(event)
        return event

    async def _persist(self, state: _State) -> None:
        """Project the current execution state into the store (if any)."""
        if self._async_store is None:
            return
        await self._async_store.upsert_execution(
            execution_id=state.execution_id,
            task_id=state.task_id,
            repo_path=str(state.repo_path),
            task_description=state.task_description,
            status=state.status.value,
            created_at=state.created_at or utc_now_iso(),
            plan=state.plan,
            error=state.error,
            decider=state.decider,
            correlation_id=(
                state.factory._correlation_id if state.factory else None
            ),
        )

    async def _emit_ai_requested(
        self, state: _State, request: AIRequest, *, purpose: str
    ) -> None:
        await self._emit(state, AI_REQUESTED, {
            "provider": self._adapter.provider_name,
            "endpoint_host": self._adapter.endpoint_host,
            "model": request.model,
            "purpose": purpose,
            "message_count": len(request.messages),
            "response_json": request.response_json,
        })

    async def _emit_ai_responded(self, state: _State, response: Any, *, purpose: str) -> None:
        await self._emit(state, AI_RESPONDED, {
            "request_id": getattr(response, "request_id", None),
            "model": getattr(response, "model", None),
            "purpose": purpose,
            "finish_reason": getattr(response, "finish_reason", None),
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            } if getattr(response, "usage", None) else {},
            "latency_ms": getattr(response, "latency_ms", 0),
            "content_bytes": len(getattr(response, "content", "") or ""),
        })

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def snapshot(self, execution_id: str) -> ExecutionSnapshot:
        return self.snapshot_from(self._require_state(execution_id))

    def snapshot_from(self, state: _State) -> ExecutionSnapshot:
        return ExecutionSnapshot(
            task_id=state.task_id,
            execution_id=state.execution_id,
            repo_path=str(state.repo_path),
            task_description=state.task_description,
            status=state.status,
            plan=state.plan,
            observations=tuple(state.observations),
            error=state.error,
        )

    def _require_state(self, execution_id: str) -> _State:
        state = self._states.get(execution_id)
        if state is None:
            raise InvalidTransitionError(
                f"unknown execution {execution_id} in this process; "
                "use replay to inspect historical executions"
            )
        return state


def _bounded(details: dict[str, Any], limit: int = 2000) -> dict[str, Any]:
    out = {}
    for key, value in details.items():
        if isinstance(value, str) and len(value) > limit:
            out[key] = value[:limit] + "...(truncated)"
        else:
            out[key] = value
    return out


def _utcnow_iso() -> str:
    return utc_now_iso()
