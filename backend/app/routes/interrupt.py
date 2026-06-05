from fastapi import APIRouter, HTTPException

from app.db.schema import InterruptRequestRecord
from app.models.interrupt import InterruptRequest
from app.models.runtime_event import EventType
from app.services.event_service import event_service
from app.services.interrupt_service import (
    InterruptRequestAlreadyResolvedError,
    InterruptRequestNotFoundError,
    interrupt_service,
)

router = APIRouter()


def to_interrupt_request(record: InterruptRequestRecord) -> InterruptRequest:
    return InterruptRequest(
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


def interrupt_metadata(record: InterruptRequestRecord) -> dict[str, object]:
    metadata = {
        "interrupt_request_id": record.id,
        "task_id": record.task_id,
        "reason": record.reason,
        "status": record.status,
        "created_at": record.created_at.isoformat(),
    }
    if record.resolved_at is not None:
        metadata["resolved_at"] = record.resolved_at.isoformat()
    return metadata


@router.get("/interrupts")
def list_interrupts(
    status: str | None = None,
    task_id: str | None = None,
) -> list[InterruptRequest]:
    return [
        to_interrupt_request(record)
        for record in interrupt_service.list_requests(
            status=status,
            task_id=task_id,
        )
    ]


@router.get("/interrupts/{request_id}")
def get_interrupt(request_id: str) -> InterruptRequest:
    try:
        return to_interrupt_request(interrupt_service.get_request(request_id))
    except InterruptRequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/interrupts/{request_id}/apply")
def apply_interrupt(request_id: str) -> InterruptRequest:
    try:
        record = interrupt_service.apply_request(request_id)
    except InterruptRequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InterruptRequestAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    event_service.emit_event_sync(
        event_type=EventType.INTERRUPT_APPLIED,
        message=f"Interrupt applied for task: {record.task_id}",
        metadata=interrupt_metadata(record),
    )
    return to_interrupt_request(record)


@router.post("/interrupts/{request_id}/ignore")
def ignore_interrupt(request_id: str) -> InterruptRequest:
    try:
        record = interrupt_service.ignore_request(request_id)
    except InterruptRequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InterruptRequestAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    event_service.emit_event_sync(
        event_type=EventType.INTERRUPT_IGNORED,
        message=f"Interrupt ignored for task: {record.task_id}",
        metadata=interrupt_metadata(record),
    )
    return to_interrupt_request(record)
