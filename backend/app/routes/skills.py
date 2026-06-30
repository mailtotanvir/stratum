from fastapi import APIRouter

from app.models.skill import SkillRegistryCatalog
from app.services.skill_registry_service import skill_registry_service

router = APIRouter()


@router.get("/runtime/skills")
def list_skills() -> SkillRegistryCatalog:
    return skill_registry_service.list_registry()
