from typing import Any

from fastapi import APIRouter

from app.services.diagnostics_service import diagnostics_service

router = APIRouter()


@router.get("/diagnostics/events")
def event_diagnostics() -> dict[str, Any]:
    return diagnostics_service.event_store_health()


@router.get("/diagnostics/proposals")
def proposal_diagnostics() -> dict[str, Any]:
    return diagnostics_service.proposal_health()


@router.get("/diagnostics/planner-recommendations")
def planner_recommendation_diagnostics() -> dict[str, Any]:
    return diagnostics_service.planner_recommendation_health()


@router.get("/diagnostics/governance")
def governance_diagnostics() -> dict[str, Any]:
    return diagnostics_service.governance_health()


@router.get("/diagnostics/summary")
def diagnostics_summary() -> dict[str, Any]:
    return diagnostics_service.runtime_summary()
