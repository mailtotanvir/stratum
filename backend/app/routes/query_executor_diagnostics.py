from fastapi import APIRouter

from app.models.query_executor_diagnostics import QueryExecutorDiagnostics
from app.services.query_executor_diagnostics_service import (
    query_executor_diagnostics_service,
)


router = APIRouter()


@router.get("/runtime/query-executor-diagnostics")
def get_runtime_query_executor_diagnostics() -> QueryExecutorDiagnostics:
    return query_executor_diagnostics_service.get_diagnostics()
