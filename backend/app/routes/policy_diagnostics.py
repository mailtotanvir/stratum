from fastapi import APIRouter

from app.models.policy_diagnostics import PolicyDiagnostics
from app.services.policy_diagnostics_service import policy_diagnostics_service


router = APIRouter()


@router.get("/runtime/policy-diagnostics")
def get_policy_diagnostics() -> PolicyDiagnostics:
    return policy_diagnostics_service.generate()
