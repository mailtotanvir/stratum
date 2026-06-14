from typing import Any

from fastapi import APIRouter, HTTPException

from app.models.governance_audit import (
    GovernanceAuditRecord,
    GovernanceAuditSummary,
)
from app.services.governance_audit_service import (
    GovernanceAuditRecordNotFoundError,
    governance_audit_service,
)
from app.services.governance_service import governance_service

router = APIRouter()


@router.get("/runtime/governance/audit")
def governance_audit() -> list[GovernanceAuditRecord]:
    return governance_audit_service.list_records()


@router.get("/runtime/governance/audit/{decision_id}")
def governance_audit_detail(
    decision_id: str,
) -> GovernanceAuditRecord:
    try:
        return governance_audit_service.get_record(decision_id)
    except GovernanceAuditRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime/governance/summary")
def governance_audit_summary() -> GovernanceAuditSummary:
    return governance_audit_service.summary()


@router.get("/governance/error-budget")
def error_budget() -> dict[str, Any]:
    return governance_service.evaluate_error_budget()


@router.get("/governance/decision-preview")
def decision_preview() -> dict[str, Any]:
    return governance_service.preview_decision()


@router.get("/governance/reflection-preview")
def reflection_preview() -> dict[str, Any]:
    return governance_service.preview_reflection()
