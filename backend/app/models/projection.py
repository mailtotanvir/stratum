from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.projection_lineage import ProjectionLineage


class ProjectionReconstructionInfo(BaseModel):
    projection_type: str = Field(min_length=1)
    reconstruction_source: str = Field(min_length=1)
    rebuildable: Literal[True] = True
    authoritative_source: str = Field(min_length=1)


class ProjectionSchemaInfo(BaseModel):
    projection_type: str = Field(min_length=1)
    schema_version: int = Field(ge=1)
    builder_name: str = Field(min_length=1)
    reconstruction: ProjectionReconstructionInfo


class ProjectionCapability(BaseModel):
    replayable: bool
    drift_checkable: bool
    reconstructable: bool
    analyzable: bool
    explainable: bool


class ProjectionContract(BaseModel):
    projection_name: str = Field(min_length=1)
    projection_version: int = Field(ge=1)
    projection_description: str = Field(min_length=1)
    projection_owner: str = Field(min_length=1)
    projection_category: str = Field(min_length=1)
    supports_replay: bool
    supports_drift_detection: bool
    supports_reconstruction: bool
    supports_analytics: bool
    supports_explainability: bool


class ProjectionRegistryEntry(BaseModel):
    projection_name: str = Field(min_length=1)
    projection_version: int = Field(ge=1)
    projection_category: str = Field(min_length=1)
    category: str = Field(min_length=1)
    route: str = Field(min_length=1)
    supported_filters: list[str] = Field(default_factory=list)
    contract: ProjectionContract
    capabilities: ProjectionCapability


class ProjectionRegistryCatalog(BaseModel):
    projections: list[ProjectionRegistryEntry]
    registered_projections_total: int = Field(ge=0)
    observability_metrics: dict[str, int] = Field(default_factory=dict)


class ProjectionRegistryDetail(ProjectionRegistryEntry):
    version_information: dict[str, int | str]
    observability_metrics: dict[str, int] = Field(default_factory=dict)


class ProjectionMetadata(ProjectionSchemaInfo):
    built_at: datetime
    source: str = Field(min_length=1)


class Projection(BaseModel):
    metadata: ProjectionMetadata


class ProjectionRebuildRequest(BaseModel):
    source: str = Field(min_length=1)


class ProjectionRebuildDiagnostic(BaseModel):
    event_type: Literal[
        "projection_rebuild_started",
        "projection_rebuild_completed",
        "projection_rebuild_failed",
    ]
    projection_type: str
    schema_version: int
    builder_name: str
    source: str
    reconstruction: ProjectionReconstructionInfo
    message: str | None = None


class ProjectionRebuildResult(BaseModel):
    projection_type: str
    schema_version: int
    builder_name: str
    source: str
    reconstruction: ProjectionReconstructionInfo
    projection_data: Any
    snapshot_manifest: "ProjectionSnapshotManifest"
    diagnostics: list[ProjectionRebuildDiagnostic]


class ProjectionDifference(BaseModel):
    field_path: str
    expected_value: Any = None
    actual_value: Any = None
    difference_type: Literal[
        "missing_field",
        "unexpected_field",
        "value_mismatch",
        "metadata_mismatch",
    ]


class ProjectionVerificationDiagnostic(BaseModel):
    event_type: Literal[
        "projection_verification_started",
        "projection_verification_completed",
        "projection_verification_failed",
    ]
    projection_name: str
    schema_version: int
    builder_name: str
    difference_count: int
    message: str | None = None


class ProjectionVerificationResult(BaseModel):
    projection_name: str
    verified: bool
    verified_at: datetime
    schema_version: int
    builder_name: str
    differences: list[ProjectionDifference]
    reconstruction_info: ProjectionReconstructionInfo
    current_manifest: "ProjectionSnapshotManifest"
    rebuilt_manifest: "ProjectionSnapshotManifest"
    hash_match: bool
    diagnostics: list[ProjectionVerificationDiagnostic]


class ProjectionSnapshotManifest(BaseModel):
    projection_name: str
    schema_version: int
    builder_name: str
    generated_at: datetime
    source_event_count: int = Field(ge=0)
    source_session_id: str
    source_runtime_id: str | None = None
    reconstruction_info: ProjectionReconstructionInfo
    verification_status: str | None = None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProjectionSnapshotExportRequest(BaseModel):
    source: str = Field(min_length=1)
    verify: bool = False
    include_lineage: bool = True


class ProjectionSnapshotExportDiagnostic(BaseModel):
    event_type: Literal[
        "projection_snapshot_export_started",
        "projection_snapshot_export_completed",
        "projection_snapshot_export_failed",
    ]
    projection_name: str
    export_id: str
    schema_version: int
    builder_name: str
    content_hash: str | None = None
    message: str | None = None


class ProjectionSnapshotExport(BaseModel):
    export_id: str
    projection_name: str
    exported_at: datetime
    projection: Any
    snapshot_manifest: ProjectionSnapshotManifest
    reconstruction_info: ProjectionReconstructionInfo
    verification_status: str | None = None
    lineage: ProjectionLineage | None = None
    diagnostics: list[ProjectionSnapshotExportDiagnostic]
