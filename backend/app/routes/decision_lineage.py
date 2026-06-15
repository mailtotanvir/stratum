from fastapi import APIRouter, HTTPException

from app.models.decision_lineage import (
    DecisionLineageChain,
    DecisionLineageEvidenceSummary,
    DecisionLineageRecord,
    DecisionLineageSummary,
)
from app.services.decision_lineage_service import (
    DecisionLineageNotFoundError,
    decision_lineage_service,
)


router = APIRouter()


@router.get("/runtime/decision-lineage")
def decision_lineage_records() -> list[DecisionLineageRecord]:
    return decision_lineage_service.list_records()


@router.get("/runtime/decision-lineage/summary")
def decision_lineage_summary() -> DecisionLineageSummary:
    return decision_lineage_service.summary()


@router.get("/runtime/decision-lineage/{decision_id}")
def decision_lineage_chain(decision_id: str) -> DecisionLineageChain:
    try:
        return decision_lineage_service.get_chain(decision_id)
    except DecisionLineageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime/decision-lineage/{decision_id}/evidence")
def decision_lineage_evidence(
    decision_id: str,
) -> DecisionLineageEvidenceSummary:
    try:
        return decision_lineage_service.evidence_summary(decision_id)
    except DecisionLineageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
