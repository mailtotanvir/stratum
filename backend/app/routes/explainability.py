from fastapi import APIRouter, HTTPException

from app.models.explainability import (
    ArtifactExplanation,
    DecisionExplanation,
    ExplanationView,
)
from app.services.explainability_service import (
    ExplainabilityService,
    ExplanationGenerationError,
    ExplanationNotFoundError,
    explainability_service,
)


router = APIRouter()


@router.get("/runtime/explainability/decisions/{decision_id}")
def explain_decision(decision_id: str) -> DecisionExplanation:
    try:
        return explainability_service.explain_decision(decision_id)
    except ExplanationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExplanationGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/runtime/explainability/artifacts/{artifact_id}")
def explain_artifact(artifact_id: str) -> ArtifactExplanation:
    try:
        return explainability_service.explain_artifact(artifact_id)
    except ExplanationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExplanationGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/runtime/explainability/sessions/{session_id}")
def explain_session(session_id: str) -> ExplanationView:
    try:
        return explainability_service.explain_session(session_id)
    except ExplanationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExplanationGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
