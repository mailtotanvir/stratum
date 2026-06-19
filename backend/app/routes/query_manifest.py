from fastapi import APIRouter

from app.models.query_manifest import QueryManifest
from app.services.query_manifest_service import query_manifest_service


router = APIRouter()


@router.get("/runtime/query-manifest")
def get_runtime_query_manifest() -> QueryManifest:
    return query_manifest_service.get_manifest()
