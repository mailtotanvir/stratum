from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.models.query_execution_record import (
    QueryHistoryDetailResponse,
    QueryHistoryResponse,
)
from app.models.query_lineage import QueryLineage
from app.models.query_snapshot_manifest import QuerySnapshotManifest
from app.models.query_snapshot_export import QuerySnapshotExport
from app.models.runtime_query import (
    RuntimeQuery,
    RuntimeQueryDiscovery,
)
from app.models.runtime_query_execution import (
    RuntimeQueryExecutionInput,
    RuntimeQueryExecutionRequest,
    RuntimeQueryExecutionResult,
)
from app.models.query_verification import QueryVerificationResult
from app.query.runtime_query_registry import (
    RuntimeQueryNotFoundError,
    runtime_query_registry,
)
from app.services.query_history_service import (
    QueryExecutionRecordNotFoundError,
    query_history_service,
)
from app.services.query_lineage_service import (
    QueryLineageGenerationError,
    query_lineage_service,
)
from app.services.query_snapshot_manifest_service import (
    QueryManifestGenerationError,
    query_snapshot_manifest_service,
)
from app.services.query_snapshot_export_service import (
    QuerySnapshotExportError,
    query_snapshot_export_service,
)
from app.services.query_verification_service import (
    QueryReconstructionMetadataError,
    QueryVerificationError,
    QueryVersionMismatchError,
    query_verification_service,
)
from app.services.runtime_query_execution_service import (
    RuntimeQueryExecutionError,
    RuntimeQueryParameterValidationError,
    runtime_query_execution_service,
)
from app.services.runtime_session_service import RuntimeSessionNotFoundError


router = APIRouter()


@router.get("/queries")
def list_runtime_queries() -> RuntimeQueryDiscovery:
    return RuntimeQueryDiscovery(
        queries=runtime_query_registry.list_queries()
    )


@router.get("/queries/history")
def get_query_history() -> QueryHistoryResponse:
    return query_history_service.retrieve_history()


@router.get("/queries/history/{execution_id}")
def get_query_history_detail(
    execution_id: str,
) -> QueryHistoryDetailResponse:
    try:
        return query_history_service.retrieve_execution(execution_id)
    except QueryExecutionRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/queries/history/{execution_id}/verify")
def verify_query_execution(
    execution_id: str,
) -> QueryVerificationResult:
    try:
        return query_verification_service.verify(execution_id)
    except QueryExecutionRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeQueryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        QueryVersionMismatchError,
        QueryReconstructionMetadataError,
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "diagnostics": [
                    diagnostic.model_dump(mode="json")
                    for diagnostic in exc.diagnostics
                ],
            },
        ) from exc
    except QueryVerificationError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": str(exc),
                "diagnostics": [
                    diagnostic.model_dump(mode="json")
                    for diagnostic in exc.diagnostics
                ],
            },
        ) from exc


@router.get("/queries/history/{execution_id}/lineage")
def get_query_execution_lineage(
    execution_id: str,
) -> QueryLineage:
    try:
        return query_lineage_service.generate(execution_id)
    except QueryExecutionRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryLineageGenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/queries/history/{execution_id}/manifest")
def get_query_execution_manifest(
    execution_id: str,
) -> QuerySnapshotManifest:
    try:
        return query_snapshot_manifest_service.generate(execution_id)
    except QueryExecutionRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryManifestGenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/queries/history/{execution_id}/export")
def export_query_execution_snapshot(
    execution_id: str,
) -> QuerySnapshotExport:
    try:
        return query_snapshot_export_service.export(execution_id)
    except QueryExecutionRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QuerySnapshotExportError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "diagnostics": [
                    diagnostic.model_dump(mode="json")
                    for diagnostic in exc.diagnostics
                ],
            },
        ) from exc


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
