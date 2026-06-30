from fastapi import APIRouter

from app.models.query_health import QueryHealth
from app.services.query_health_service import query_health_service


router = APIRouter()


@router.get("/runtime/query-health")
@router.get("/runtime/queries/health")
def get_runtime_query_health() -> QueryHealth:
    return query_health_service.get_health()
