import hashlib
import json
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.models.agent_loop import (
    AgentLoopApprovalRequest,
    AgentLoopApprovalResumeResult,
    AgentLoopApprovalResponseRequest,
    AgentLoopApprovalStatus,
    AgentLoopRequest,
    AgentLoopResult,
    AgentLoopRunSummary,
    AgentLoopSmokeRequest,
    AgentLoopStatus,
    AgentLoopStopRequest,
    AgentLoopStopResponse,
)
from app.models.runtime_event import EventType, RuntimeEvent
from app.services.agent_loop_service import (
    AgentLoopApprovalNotFoundError,
    AgentLoopApprovalPendingError,
    AgentLoopService,
    AgentLoopWorkspaceNotFoundError,
)
from app.services.event_service import event_service
from app.services.provider_execution_service import (
    ProviderExecutionService,
    provider_execution_service_default,
)


router = APIRouter(tags=["agent-loop"])


def get_agent_loop_provider_execution_service() -> ProviderExecutionService:
    return provider_execution_service_default(events=event_service)


def get_agent_loop_service(
    provider_execution: ProviderExecutionService = Depends(
        get_agent_loop_provider_execution_service
    ),
) -> AgentLoopService:
    return AgentLoopService(
        provider_execution=provider_execution,
        events=event_service,
    )


@router.post(
    "/agent-loop/run",
    summary="Run the agent loop",
    response_model=AgentLoopResult,
)
def run_agent_loop(
    request: AgentLoopRequest,
    service: AgentLoopService = Depends(get_agent_loop_service),
) -> AgentLoopResult:
    try:
        return service.run(request)
    except AgentLoopWorkspaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/agent-loop/smoke",
    summary="Run an agent loop smoke test",
    response_model=AgentLoopResult,
)
def smoke_agent_loop(
    request: AgentLoopSmokeRequest,
    service: AgentLoopService = Depends(get_agent_loop_service),
) -> AgentLoopResult:
    session_id = request.session_id or _smoke_session_id(request)
    return service.run(
        AgentLoopRequest(
            session_id=session_id,
            user_request=request.user_request,
            max_iterations=request.max_iterations,
            workspace_id=request.workspace_id,
            provider_id=request.provider_id,
            model=request.model,
        )
    )


@router.post(
    "/agent-loop/{session_id}/stop",
    summary="Request agent loop stop",
    response_model=AgentLoopStopResponse,
)
def stop_agent_loop(
    session_id: str,
    request: AgentLoopStopRequest | None = None,
) -> AgentLoopStopResponse:
    _require_agent_loop_run(session_id)
    metadata: dict[str, Any] = {"session_id": session_id}
    if request is not None and request.reason is not None:
        metadata["reason"] = request.reason
    event_service.emit_event_sync(
        event_type=EventType.AGENT_LOOP_STOP_REQUESTED,
        message="Agent loop stop requested",
        metadata=metadata,
    )
    return AgentLoopStopResponse(
        session_id=session_id,
        stop_requested=True,
    )


@router.post(
    "/agent-loop/approvals/{approval_id}/respond",
    summary="Respond to an agent loop approval request",
    response_model=AgentLoopApprovalRequest,
)
def respond_to_agent_loop_approval(
    approval_id: str,
    request: AgentLoopApprovalResponseRequest,
) -> AgentLoopApprovalRequest:
    approval = _find_approval_request(approval_id)
    if approval is None:
        raise HTTPException(
            status_code=404,
            detail="Agent loop approval request not found",
        )

    status = (
        AgentLoopApprovalStatus.APPROVED
        if request.approved
        else AgentLoopApprovalStatus.REJECTED
    )
    metadata: dict[str, Any] = {
        "approval_id": approval_id,
        "session_id": approval.session_id,
        "status": status.value,
    }
    if request.reason is not None:
        metadata["reason"] = request.reason
    event_service.emit_event_sync(
        event_type=EventType.AGENT_LOOP_APPROVAL_RESPONDED,
        message="Agent loop approval responded",
        metadata=metadata,
    )
    return approval.model_copy(
        update={"status": status, "reason": request.reason}
    )


@router.post(
    "/agent-loop/approvals/{approval_id}/resume",
    summary="Resume an agent loop approval",
    response_model=AgentLoopApprovalResumeResult,
)
def resume_agent_loop_approval(
    approval_id: str,
    service: AgentLoopService = Depends(get_agent_loop_service),
) -> AgentLoopApprovalResumeResult:
    try:
        return service.resume_approval(approval_id)
    except AgentLoopApprovalNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Agent loop approval request not found",
        ) from exc
    except AgentLoopApprovalPendingError as exc:
        raise HTTPException(
            status_code=409,
            detail="Agent loop approval response pending",
        ) from exc


@router.post(
    "/agent-loop/approvals/{approval_id}/continue",
    summary="Continue an agent loop approval",
    response_model=AgentLoopResult | AgentLoopApprovalResumeResult,
)
def continue_agent_loop_approval(
    approval_id: str,
    service: AgentLoopService = Depends(get_agent_loop_service),
) -> AgentLoopResult | AgentLoopApprovalResumeResult:
    try:
        return service.continue_approval(approval_id)
    except AgentLoopApprovalNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Agent loop approval request not found",
        ) from exc
    except AgentLoopApprovalPendingError as exc:
        raise HTTPException(
            status_code=409,
            detail="Agent loop approval response pending",
        ) from exc


@router.get(
    "/agent-loop/events/{session_id}/stream",
    summary="Stream agent loop events as SSE",
)
def stream_agent_loop_events(session_id: str) -> StreamingResponse:
    _require_agent_loop_run(session_id)
    events = _list_agent_loop_events(session_id)

    def event_stream() -> Iterator[str]:
        for event in events:
            yield _format_agent_loop_sse(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.get(
    "/agent-loop/events/{session_id}",
    summary="List agent loop events",
)
def list_agent_loop_events(session_id: str) -> list[dict[str, Any]]:
    _require_agent_loop_run(session_id)
    return [
        _serialize_agent_loop_event(event)
        for event in _list_agent_loop_events(session_id)
    ]


@router.get(
    "/agent-loop/runs",
    summary="List agent loop runs",
)
def list_agent_loop_run_summaries(
    status: AgentLoopStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AgentLoopRunSummary]:
    events_by_session: dict[str, list[RuntimeEvent]] = {}
    for event in event_service.list_persisted_events():
        session_id = event.metadata.get("session_id")
        if _is_agent_loop_event(event) and isinstance(session_id, str):
            events_by_session.setdefault(session_id, []).append(event)

    summaries = [
        _reconstruct_agent_loop_run_summary(session_id, events)
        for session_id, events in events_by_session.items()
        if _contains_started_event(events)
    ]
    if status is not None:
        summaries = [
            summary for summary in summaries if summary.status == status
        ]

    summaries.sort(key=lambda summary: summary.session_id)
    summaries.sort(
        key=lambda summary: summary.started_at or "",
        reverse=True,
    )
    return summaries[:limit]


@router.get(
    "/agent-loop/runs/{session_id}",
    summary="Get an agent loop run",
    response_model=AgentLoopRunSummary,
)
def get_agent_loop_run_summary(session_id: str) -> AgentLoopRunSummary:
    events = _list_agent_loop_events(session_id)
    if not _contains_started_event(events):
        raise HTTPException(status_code=404, detail="Agent loop run not found")

    return _reconstruct_agent_loop_run_summary(session_id, events)


def _reconstruct_agent_loop_run_summary(
    session_id: str,
    events: list[RuntimeEvent],
) -> AgentLoopRunSummary:
    summary: dict[str, Any] = {
        "session_id": session_id,
        "status": AgentLoopStatus.RUNNING,
        "iterations_used": 0,
    }
    for event in events:
        metadata = event.metadata
        if event.type == EventType.AGENT_LOOP_STARTED:
            summary.update(
                status=AgentLoopStatus.RUNNING,
                user_request=metadata.get("user_request"),
                workspace_id=metadata.get("workspace_id"),
                workspace_root_path=metadata.get("workspace_root_path"),
                provider_id=metadata.get("provider_id"),
                model=metadata.get("model"),
                iterations_used=0,
                final_answer=None,
                error=None,
                started_at=event.ts,
                completed_at=None,
                stopped_at=None,
            )
        elif event.type == EventType.AGENT_LOOP_COMPLETED:
            summary.update(
                status=AgentLoopStatus.COMPLETED,
                final_answer=metadata.get("final_answer"),
                iterations_used=metadata.get("iterations_used", 0),
                completed_at=event.ts,
            )
        elif event.type == EventType.AGENT_LOOP_FAILED:
            summary.update(
                status=AgentLoopStatus.FAILED,
                error=metadata.get("error"),
                iterations_used=metadata.get("iterations_used", 0),
                completed_at=event.ts,
            )
        elif event.type == EventType.AGENT_LOOP_STOPPED:
            summary.update(
                status=AgentLoopStatus.STOPPED,
                iterations_used=metadata.get("iterations_used", 0),
                stopped_at=event.ts,
            )
        elif event.type == EventType.AGENT_LOOP_APPROVAL_REQUESTED:
            summary.update(
                status=AgentLoopStatus.PAUSED,
                iterations_used=metadata.get("iteration", 0),
            )

    return AgentLoopRunSummary.model_validate(summary)


def _require_agent_loop_run(session_id: str) -> None:
    if not _contains_started_event(_list_agent_loop_events(session_id)):
        raise HTTPException(status_code=404, detail="Agent loop run not found")


def _list_agent_loop_events(session_id: str) -> list[RuntimeEvent]:
    return [
        event
        for event in event_service.list_persisted_events()
        if _is_agent_loop_event(event, session_id)
    ]


def _is_agent_loop_event(
    event: RuntimeEvent,
    session_id: str | None = None,
) -> bool:
    return (
        event.type.value.startswith("agent_loop_")
        and (
            session_id is None
            or event.metadata.get("session_id") == session_id
        )
    )


def _contains_started_event(events: list[RuntimeEvent]) -> bool:
    return any(
        event.type == EventType.AGENT_LOOP_STARTED for event in events
    )


def _find_approval_request(
    approval_id: str,
) -> AgentLoopApprovalRequest | None:
    for event in reversed(
        event_service.list_persisted_events(
            event_type=EventType.AGENT_LOOP_APPROVAL_REQUESTED.value
        )
    ):
        if event.metadata.get("approval_id") == approval_id:
            return AgentLoopApprovalRequest.model_validate(event.metadata)
    return None


def _serialize_agent_loop_event(event: RuntimeEvent) -> dict[str, Any]:
    return event.to_dict()


def _format_agent_loop_sse(event: RuntimeEvent) -> str:
    payload = json.dumps(
        _serialize_agent_loop_event(event),
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"event: {event.type.value}\ndata: {payload}\n\n"


def _smoke_session_id(request: AgentLoopSmokeRequest) -> str:
    payload = request.model_dump(exclude={"session_id"}, mode="json")
    canonical_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical_payload.encode()).hexdigest()[:16]
    return f"agent-loop-smoke-{digest}"
