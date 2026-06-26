from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.projection import ProjectionRebuildResult
from app.models.projection_replay import ProjectionReplayRequest
from app.runtime.projection_registry import (
    ProjectionRegistry,
    projection_registry,
)
from app.services.projection_rebuild_service import (
    ProjectionRebuildError,
    ProjectionRebuildService,
    projection_rebuild_service,
)
from app.services.projection_replay_service import (
    ProjectionReplayError,
    ProjectionReplayService,
    projection_replay_service,
)


EVALUATION_RECONSTRUCTION_PROJECTIONS = [
    "evaluation_coverage",
    "evaluation_drift",
    "evaluation_intelligence_overview",
    "evaluation_lineage",
    "evaluation_registry",
]
EVALUATION_RECONSTRUCTION_SOURCE = "runtime_event_store"


class EvaluationProjectionReconstructionMetadata(BaseModel):
    projection_name: str = Field(min_length=1)
    rebuild_supported: bool
    reconstruction_source: str = Field(min_length=1)
    reconstruction_status: str = Field(min_length=1)
    reconstructed_record_count: int = Field(ge=0)
    last_reconstruction_time: datetime | None = None
    replay_verified: bool


class EvaluationReconstructionResult(BaseModel):
    projections: list[EvaluationProjectionReconstructionMetadata]
    total_projections: int = Field(ge=0)
    successful_reconstructions: int = Field(ge=0)
    failed_reconstructions: int = Field(ge=0)
    replay_validation_status: str = Field(min_length=1)
    generated_at: datetime


class EvaluationReconstructionService:
    def __init__(
        self,
        registry: ProjectionRegistry | None = None,
        rebuilds: ProjectionRebuildService | None = None,
        replay: ProjectionReplayService | None = None,
    ) -> None:
        self._registry = registry or projection_registry
        self._rebuilds = rebuilds or projection_rebuild_service
        self._replay = replay or projection_replay_service

    def inspect(self) -> EvaluationReconstructionResult:
        projections = [
            self._inspect_projection(projection_name)
            for projection_name in EVALUATION_RECONSTRUCTION_PROJECTIONS
        ]
        return self._result(projections)

    def rebuild_all(self) -> EvaluationReconstructionResult:
        projections = [
            self._rebuild_projection(projection_name)
            for projection_name in EVALUATION_RECONSTRUCTION_PROJECTIONS
        ]
        return self._result(projections)

    def rebuild_projection(
        self,
        projection_name: str,
    ) -> ProjectionRebuildResult:
        return self._rebuilds.rebuild(
            projection_name,
            EVALUATION_RECONSTRUCTION_SOURCE,
        )

    def _inspect_projection(
        self,
        projection_name: str,
    ) -> EvaluationProjectionReconstructionMetadata:
        schema = self._registry.get_schema(projection_name)
        return EvaluationProjectionReconstructionMetadata(
            projection_name=projection_name,
            rebuild_supported=schema.reconstruction.rebuildable,
            reconstruction_source=schema.reconstruction.reconstruction_source,
            reconstruction_status="not_rebuilt",
            reconstructed_record_count=0,
            last_reconstruction_time=None,
            replay_verified=False,
        )

    def _rebuild_projection(
        self,
        projection_name: str,
    ) -> EvaluationProjectionReconstructionMetadata:
        schema = self._registry.get_schema(projection_name)
        try:
            first = self._rebuilds.rebuild(
                projection_name,
                EVALUATION_RECONSTRUCTION_SOURCE,
            )
            second = self._rebuilds.rebuild(
                projection_name,
                EVALUATION_RECONSTRUCTION_SOURCE,
            )
            replay = self._replay.preview(
                ProjectionReplayRequest(projection_name=projection_name)
            )
            deterministic = (
                _stable_projection(first.projection_data)
                == _stable_projection(second.projection_data)
                and replay.status == "completed"
            )
            return EvaluationProjectionReconstructionMetadata(
                projection_name=projection_name,
                rebuild_supported=schema.reconstruction.rebuildable,
                reconstruction_source=(
                    schema.reconstruction.reconstruction_source
                ),
                reconstruction_status=(
                    "completed" if deterministic else "failed"
                ),
                reconstructed_record_count=_record_count(
                    first.projection_data
                ),
                last_reconstruction_time=first.snapshot_manifest.generated_at,
                replay_verified=deterministic,
            )
        except (ProjectionRebuildError, ProjectionReplayError):
            return EvaluationProjectionReconstructionMetadata(
                projection_name=projection_name,
                rebuild_supported=schema.reconstruction.rebuildable,
                reconstruction_source=(
                    schema.reconstruction.reconstruction_source
                ),
                reconstruction_status="failed",
                reconstructed_record_count=0,
                last_reconstruction_time=None,
                replay_verified=False,
            )

    @staticmethod
    def _result(
        projections: list[EvaluationProjectionReconstructionMetadata],
    ) -> EvaluationReconstructionResult:
        successful = sum(
            1
            for projection in projections
            if projection.reconstruction_status == "completed"
        )
        failed = sum(
            1
            for projection in projections
            if projection.reconstruction_status == "failed"
        )
        replay_verified = all(
            projection.replay_verified for projection in projections
        )
        return EvaluationReconstructionResult(
            projections=projections,
            total_projections=len(projections),
            successful_reconstructions=successful,
            failed_reconstructions=failed,
            replay_validation_status=(
                "verified" if replay_verified else "not_verified"
            ),
            generated_at=datetime.now(UTC),
        )


def _stable_projection(projection: Any) -> dict[str, Any]:
    if hasattr(projection, "model_dump"):
        dumped = projection.model_dump(mode="json")
    else:
        dumped = projection
    if isinstance(dumped, dict):
        dumped = dict(dumped)
        metadata = dumped.get("metadata")
        if isinstance(metadata, dict):
            metadata = dict(metadata)
            metadata.pop("built_at", None)
            dumped["metadata"] = metadata
        dumped.pop("generated_at", None)
    return dumped


def _record_count(projection: Any) -> int:
    dumped = (
        projection.model_dump(mode="json")
        if hasattr(projection, "model_dump")
        else projection
    )
    if not isinstance(dumped, dict):
        return 0
    total_fields = [
        value
        for key, value in dumped.items()
        if key.startswith("total_") and isinstance(value, int)
    ]
    if total_fields:
        return max(total_fields)
    return sum(
        len(value)
        for value in dumped.values()
        if isinstance(value, list)
    )


evaluation_reconstruction_service = EvaluationReconstructionService()
