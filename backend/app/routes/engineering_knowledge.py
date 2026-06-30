from fastapi import APIRouter

from app.models.engineering_knowledge import EngineeringKnowledgeCatalog
from app.services.engineering_knowledge_service import (
    engineering_knowledge_service,
)

router = APIRouter()


@router.get("/runtime/engineering-knowledge")
def get_engineering_knowledge() -> EngineeringKnowledgeCatalog:
    return engineering_knowledge_service.build()

