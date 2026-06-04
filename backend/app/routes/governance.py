from typing import Any

from fastapi import APIRouter

from app.services.governance_service import governance_service

router = APIRouter()


@router.get("/governance/error-budget")
def error_budget() -> dict[str, Any]:
    return governance_service.evaluate_error_budget()


@router.get("/governance/decision-preview")
def decision_preview() -> dict[str, Any]:
    return governance_service.preview_decision()


@router.get("/governance/reflection-preview")
def reflection_preview() -> dict[str, Any]:
    return governance_service.preview_reflection()
