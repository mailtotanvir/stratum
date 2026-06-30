from fastapi import APIRouter
from fastapi import HTTPException

from app.models.skill import (
    SkillManifestDiagnostics,
    SkillRegistryCatalog,
    SkillRegistryDiagnostic,
)
from app.services.skill_registry_service import skill_registry_service

router = APIRouter()


@router.get("/runtime/skills")
def list_skills() -> SkillRegistryCatalog:
    return skill_registry_service.list_registry()


@router.get("/runtime/skills/{skill_id}/diagnostics")
def skill_diagnostics(skill_id: str) -> SkillManifestDiagnostics:
    try:
        return skill_registry_service.diagnostics_for(skill_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}") from exc


@router.get("/runtime/skills/diagnostics")
def registry_diagnostics() -> SkillRegistryDiagnostic:
    return skill_registry_service.diagnostics()
