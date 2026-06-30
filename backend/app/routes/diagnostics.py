from typing import Any

from fastapi import APIRouter

from app.services.cognitive_state_service import cognitive_state_service
from app.services.diagnostics_service import diagnostics_service
from app.services.memory_reconstruction_service import memory_reconstruction_service
from app.services.skill_registry_service import skill_registry_service

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


@router.get("/diagnostics/decision-records")
def decision_record_diagnostics() -> dict[str, Any]:
    return diagnostics_service.decision_record_health()


@router.get("/diagnostics/decision-evidence")
def decision_evidence_diagnostics() -> dict[str, Any]:
    return diagnostics_service.decision_evidence_health()


@router.get("/diagnostics/decision-trails")
def decision_trail_diagnostics() -> dict[str, Any]:
    return diagnostics_service.decision_trail_health()


@router.get("/diagnostics/cognitive-state")
def cognitive_state_diagnostics() -> dict[str, object]:
    return cognitive_state_service.diagnostics()


@router.get("/diagnostics/governance")
def governance_diagnostics() -> dict[str, Any]:
    return diagnostics_service.governance_health()


@router.get("/diagnostics/summary")
def diagnostics_summary() -> dict[str, Any]:
    return diagnostics_service.runtime_summary()


@router.get("/diagnostics/skills")
def skill_registry_diagnostics() -> dict[str, Any]:
    return skill_registry_service.diagnostics().model_dump(mode="json")


@router.get("/diagnostics/memory")
def memory_diagnostics() -> dict[str, Any]:
    return memory_reconstruction_service.diagnostics().model_dump(mode="json")
