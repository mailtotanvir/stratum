from fastapi import APIRouter

from app.models.query_catalog import QueryCatalog
from app.services.query_catalog_service import query_catalog_service


router = APIRouter()


@router.get("/runtime/query-catalog")
def get_runtime_query_catalog() -> QueryCatalog:
    return query_catalog_service.get_catalog()
