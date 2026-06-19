from fastapi import APIRouter

from app.models.evaluation_policy_diagnostics import (
    EvaluationPolicyDiagnostics,
)
from app.services.evaluation_policy_diagnostics_service import (
    evaluation_policy_diagnostics_service,
)


router = APIRouter()


@router.get("/runtime/evaluation-policy-diagnostics")
def get_evaluation_policy_diagnostics() -> EvaluationPolicyDiagnostics:
    return evaluation_policy_diagnostics_service.generate()
