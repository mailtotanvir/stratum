from fastapi import APIRouter, HTTPException

from app.models.execution_participant import (
    ExecutionCapabilityRouteRequest,
    ExecutionLifecycleActionRequest,
    ExecutionParticipant,
)
from app.services.execution_participant_registry_service import (
    execution_participant_registry_service,
)

router = APIRouter()


@router.get("/runtime/execution-participants")
def list_execution_participants() -> list[ExecutionParticipant]:
    return execution_participant_registry_service.list_participants()


@router.get("/runtime/execution-participants/diagnostics")
def get_execution_participant_diagnostics():
    return execution_participant_registry_service.diagnostics()


@router.post("/runtime/execution-participants/route")
def route_execution_participant(request: ExecutionCapabilityRouteRequest):
    return execution_participant_registry_service.route_capability(request)


@router.get("/runtime/execution-participants/{participant_id}")
def get_execution_participant(participant_id: str) -> ExecutionParticipant:
    try:
        return execution_participant_registry_service.get_participant(participant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime/execution-invocations")
def list_execution_invocations():
    return execution_participant_registry_service.list_invocations()


@router.post("/runtime/execution-invocations")
def create_execution_invocation(request: ExecutionCapabilityRouteRequest):
    try:
        return execution_participant_registry_service.create_invocation(
            capability_id=request.capability_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runtime/execution-invocations/{invocation_id}/start")
def start_execution_invocation(invocation_id: str):
    try:
        return execution_participant_registry_service.start_invocation(invocation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runtime/execution-invocations/{invocation_id}/complete")
def complete_execution_invocation(invocation_id: str, request: ExecutionLifecycleActionRequest):
    try:
        return execution_participant_registry_service.complete_invocation(
            invocation_id,
            output_payload=request.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runtime/execution-invocations/{invocation_id}/fail")
def fail_execution_invocation(invocation_id: str, request: ExecutionLifecycleActionRequest):
    try:
        return execution_participant_registry_service.fail_invocation(
            invocation_id,
            error=request.reason or "failed",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runtime/execution-invocations/{invocation_id}/cancel")
def cancel_execution_invocation(invocation_id: str, request: ExecutionLifecycleActionRequest):
    try:
        return execution_participant_registry_service.cancel_invocation(
            invocation_id,
            reason=request.reason or "cancelled",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runtime/execution-invocations/{invocation_id}/interrupt")
def interrupt_execution_invocation(invocation_id: str, request: ExecutionLifecycleActionRequest):
    try:
        return execution_participant_registry_service.interrupt_invocation(
            invocation_id,
            reason=request.reason or "interrupted",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

