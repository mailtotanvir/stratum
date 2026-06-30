from fastapi import APIRouter

from app.models.skill import SkillRegistryCatalog, SkillManifestDiagnostics
from app.services.skill_registry_service import skill_registry_service

router = APIRouter()


@router.get("/runtime/skills")
def list_skills() -> SkillRegistryCatalog:
    return skill_registry_service.list_registry()


@router.get("/runtime/skills/{skill_id}/diagnostics")
def skill_diagnostics(skill_id: str) -> SkillManifestDiagnostics:
    return skill_registry_service.diagnostics_for(skill_id)
