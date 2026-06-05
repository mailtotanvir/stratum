from fastapi import APIRouter, HTTPException

from app.db.schema import StopRequestRecord
from app.models.runtime_event import EventType
from app.models.stop import StopRequest
from app.services.event_service import event_service
from app.services.stop_service import (
    StopRequestAlreadyResolvedError,
    StopRequestNotFoundError,
    stop_service,
)

router = APIRouter()


def to_stop_request(record: StopRequestRecord) -> StopRequest:
    return StopRequest(
        id=record.id,
        task_id=record.task_id,
        reason=record.reason,
        status=record.status,
        created_at=record.created_at.isoformat(),
        resolved_at=(
            record.resolved_at.isoformat()
            if record.resolved_at is not None
            else None
        ),
    )


def stop_metadata(record: StopRequestRecord) -> dict[str, object]:
    metadata = {
        "stop_request_id": record.id,
        "task_id": record.task_id,
        "reason": record.reason,
        "status": record.status,
        "created_at": record.created_at.isoformat(),
    }
    if record.resolved_at is not None:
        metadata["resolved_at"] = record.resolved_at.isoformat()
    return metadata


@router.get("/stops")
def list_stops(
    status: str | None = None,
    task_id: str | None = None,
) -> list[StopRequest]:
    return [
        to_stop_request(record)
        for record in stop_service.list_requests(
            status=status,
            task_id=task_id,
        )
    ]


@router.get("/stops/{request_id}")
def get_stop(request_id: str) -> StopRequest:
    try:
        return to_stop_request(stop_service.get_request(request_id))
    except StopRequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/stops/{request_id}/apply")
def apply_stop(request_id: str) -> StopRequest:
    try:
        record = stop_service.apply_request(request_id)
    except StopRequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StopRequestAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    event_service.emit_event_sync(
        event_type=EventType.STOP_APPLIED,
        message=f"Stop applied for task: {record.task_id}",
        metadata=stop_metadata(record),
    )
    return to_stop_request(record)


@router.post("/stops/{request_id}/ignore")
def ignore_stop(request_id: str) -> StopRequest:
    try:
        record = stop_service.ignore_request(request_id)
    except StopRequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StopRequestAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    event_service.emit_event_sync(
        event_type=EventType.STOP_IGNORED,
        message=f"Stop ignored for task: {record.task_id}",
        metadata=stop_metadata(record),
    )
    return to_stop_request(record)
