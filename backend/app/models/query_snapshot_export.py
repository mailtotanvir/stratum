from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.query_execution_record import (
    QueryExecutionRecord,
    QueryReconstructionInfo,
)
from app.models.query_lineage import QueryLineage
from app.models.query_snapshot_manifest import QuerySnapshotManifest


class QuerySnapshotVerificationStatus(BaseModel):
    status: Literal["verified", "drifted"]
    verified: bool
    difference_count: int = Field(ge=0)


class QuerySnapshotExportDiagnostic(BaseModel):
    event_type: Literal[
        "query_snapshot_export_started",
        "query_snapshot_export_completed",
        "query_snapshot_export_failed",
    ]
    execution_id: str
    query_name: str | None
    query_version: int | None
    export_id: str
    content_hash: str | None = None
    message: str | None = None


class QuerySnapshotExport(BaseModel):
    export_id: str
    execution_id: str
    exported_at: datetime
    query_execution_record: QueryExecutionRecord
    reconstruction_info: QueryReconstructionInfo
    lineage: QueryLineage
    manifest: QuerySnapshotManifest
    verification_status: QuerySnapshotVerificationStatus | None = None
    diagnostics: list[QuerySnapshotExportDiagnostic]
