from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.models.query_execution_record import QueryReconstructionInfo
from app.models.query_lineage import QueryLineage
from app.models.query_snapshot_manifest import QuerySnapshotManifest


class QueryDifference(BaseModel):
    field_path: str
    expected_value: Any = None
    actual_value: Any = None
    difference_type: Literal[
        "missing_field",
        "unexpected_field",
        "value_mismatch",
        "metadata_mismatch",
        "result_summary_mismatch",
    ]


class QueryVerificationDiagnostic(BaseModel):
    event_type: Literal[
        "query_verification_started",
        "query_verification_completed",
        "query_verification_failed",
    ]
    execution_id: str
    query_name: str | None
    query_version: int | None
    verified: bool
    difference_count: int
    message: str | None = None


class QueryVerificationResult(BaseModel):
    execution_id: str
    query_name: str
    query_version: int
    verified: bool
    verified_at: datetime
    original_result_summary: Any = None
    rebuilt_result_summary: Any = None
    differences: list[QueryDifference]
    reconstruction_info: QueryReconstructionInfo
    diagnostics: list[QueryVerificationDiagnostic]
    lineage: QueryLineage | None = None
    current_manifest: QuerySnapshotManifest | None = None
    rebuilt_manifest: QuerySnapshotManifest | None = None
    hash_match: bool | None = None
