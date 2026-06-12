from fastapi import APIRouter, HTTPException

from app.models.runtime_query import (
    RuntimeQuery,
    RuntimeQueryDiscovery,
)
from app.models.runtime_query_execution import (
    RuntimeQueryExecutionInput,
    RuntimeQueryExecutionRequest,
    RuntimeQueryExecutionResult,
)
from app.query.runtime_query_registry import (
    RuntimeQueryNotFoundError,
    runtime_query_registry,
)
from app.services.runtime_session_service import RuntimeSessionNotFoundError
from app.services.runtime_query_execution_service import (
    RuntimeQueryExecutionError,
    RuntimeQueryParameterValidationError,
    runtime_query_execution_service,
)
from datetime import UTC, datetime


router = APIRouter()


@router.get("/queries")
def list_runtime_queries() -> RuntimeQueryDiscovery:
    return RuntimeQueryDiscovery(
        queries=runtime_query_registry.list_queries()
    )


@router.get("/queries/{query_name}")
def get_runtime_query(query_name: str) -> RuntimeQuery:
    try:
        return runtime_query_registry.get_metadata(query_name)
    except RuntimeQueryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/queries/{query_name}/execute")
def execute_runtime_query(
    query_name: str,
    request: RuntimeQueryExecutionInput,
) -> RuntimeQueryExecutionResult:
    try:
        return runtime_query_execution_service.execute(
            RuntimeQueryExecutionRequest(
                query_name=query_name,
                parameters=request.parameters,
                execution_context=request.execution_context,
                requested_at=request.requested_at or datetime.now(UTC),
            )
        )
    except RuntimeQueryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeQueryParameterValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "query_name": exc.query_name,
                "issues": [
                    issue.model_dump(mode="json")
                    for issue in exc.issues
                ],
            },
        ) from exc
    except RuntimeQueryExecutionError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": str(exc),
                "query_name": exc.query_name,
                "execution_id": exc.execution_id,
                "diagnostics": [
                    diagnostic.model_dump(mode="json")
                    for diagnostic in exc.diagnostics
                ],
            },
        ) from exc
