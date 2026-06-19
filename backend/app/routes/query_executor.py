from fastapi import APIRouter, HTTPException

from app.models.query_executor import (
    QueryExecutionRequest,
    QueryExecutionResult,
)
from app.services.query_executor_service import (
    QueryExecutionError,
    QueryExecutionNotFoundError,
    query_executor_service,
)


router = APIRouter()


@router.post("/runtime/query-execute")
def execute_runtime_query(
    request: QueryExecutionRequest,
) -> QueryExecutionResult:
    try:
        return query_executor_service.execute(request)
    except QueryExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
