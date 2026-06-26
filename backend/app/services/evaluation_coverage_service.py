from datetime import datetime

from app.models.evaluation_coverage import (
    CoverageMapping,
    CoverageMappingCreate,
    CoverageTarget,
    CoverageTargetCreate,
    EvaluationCoverageProjection,
)
from app.models.projection import ProjectionMetadata
from app.services.event_service import EventService, event_service


EVALUATION_COVERAGE_TARGET_REGISTERED = (
    "evaluation_coverage_target_registered"
)
EVALUATION_COVERAGE_MAPPING_REGISTERED = (
    "evaluation_coverage_mapping_registered"
)


class CoverageTargetAlreadyExistsError(ValueError):
    pass


class CoverageTargetNotFoundError(LookupError):
    pass


class CoverageMappingAlreadyExistsError(ValueError):
    pass


class CoverageMappingNotFoundError(LookupError):
    pass


class EvaluationCoverageService:
    def __init__(
        self,
        events: EventService | None = None,
    ) -> None:
        self._events = events or event_service

    def register_target(
        self,
        request: CoverageTargetCreate,
    ) -> CoverageTarget:
        targets = self.list_targets()
        target_id = request.target_id or f"coverage-target-{len(targets) + 1}"
        if target_id in {target.target_id for target in targets}:
            raise CoverageTargetAlreadyExistsError(
                f"Coverage target already registered: {target_id}"
            )

        event = self._events.emit_event_sync(
            event_type=EVALUATION_COVERAGE_TARGET_REGISTERED,
            message="Evaluation coverage target registered",
            metadata={
                **request.model_dump(exclude={"target_id"}),
                "target_id": target_id,
            },
        )
        return _target_from_event_metadata(event.metadata, event.ts)

    def register_mapping(
        self,
        request: CoverageMappingCreate,
    ) -> CoverageMapping:
        mappings = self.list_mappings()
        mapping_id = (
            request.mapping_id or f"coverage-mapping-{len(mappings) + 1}"
        )
        if mapping_id in {mapping.mapping_id for mapping in mappings}:
            raise CoverageMappingAlreadyExistsError(
                f"Coverage mapping already registered: {mapping_id}"
            )
        if request.target_id not in {
            target.target_id
            for target in self.list_targets()
        }:
            raise CoverageTargetNotFoundError(
                f"Coverage target not found: {request.target_id}"
            )

        event = self._events.emit_event_sync(
            event_type=EVALUATION_COVERAGE_MAPPING_REGISTERED,
            message="Evaluation coverage mapping registered",
            metadata={
                **request.model_dump(exclude={"mapping_id"}),
                "mapping_id": mapping_id,
            },
        )
        return _mapping_from_event_metadata(event.metadata, event.ts)

    def get_target(self, target_id: str) -> CoverageTarget:
        for target in self.list_targets():
            if target.target_id == target_id:
                return target
        raise CoverageTargetNotFoundError(
            f"Coverage target not found: {target_id}"
        )

    def list_targets(self) -> list[CoverageTarget]:
        return sorted(
            [
                _target_from_event_metadata(event.metadata, event.ts)
                for event in self._events.list_persisted_events(
                    event_type=EVALUATION_COVERAGE_TARGET_REGISTERED
                )
            ],
            key=lambda target: (target.created_at, target.target_id),
        )

    def get_mapping(self, mapping_id: str) -> CoverageMapping:
        for mapping in self.list_mappings():
            if mapping.mapping_id == mapping_id:
                return mapping
        raise CoverageMappingNotFoundError(
            f"Coverage mapping not found: {mapping_id}"
        )

    def list_mappings(
        self,
        target_id: str | None = None,
    ) -> list[CoverageMapping]:
        mappings = sorted(
            [
                _mapping_from_event_metadata(event.metadata, event.ts)
                for event in self._events.list_persisted_events(
                    event_type=EVALUATION_COVERAGE_MAPPING_REGISTERED
                )
            ],
            key=lambda mapping: (mapping.created_at, mapping.mapping_id),
        )
        if target_id is not None:
            mappings = [
                mapping
                for mapping in mappings
                if mapping.target_id == target_id
            ]
        return mappings

    def build_projection(
        self,
        *,
        metadata: ProjectionMetadata,
        generated_at: datetime,
    ) -> EvaluationCoverageProjection:
        targets = self.list_targets()
        mappings = self.list_mappings()
        mapped_target_ids = {
            mapping.target_id
            for mapping in mappings
        }
        covered_targets = [
            target
            for target in targets
            if target.target_id in mapped_target_ids
        ]
        uncovered_targets = [
            target
            for target in targets
            if target.target_id not in mapped_target_ids
        ]
        total_targets = len(targets)
        coverage_percentage = (
            len(covered_targets) / total_targets * 100
            if total_targets
            else 0.0
        )
        return EvaluationCoverageProjection(
            metadata=metadata,
            targets=targets,
            mappings=mappings,
            covered_targets=covered_targets,
            uncovered_targets=uncovered_targets,
            total_targets=total_targets,
            coverage_percentage=coverage_percentage,
            generated_at=generated_at,
        )


def _target_from_event_metadata(
    metadata: dict,
    created_at: str,
) -> CoverageTarget:
    return CoverageTarget(
        target_id=str(metadata["target_id"]),
        target_name=str(metadata["target_name"]),
        target_type=str(metadata["target_type"]),
        target_category=str(metadata["target_category"]),
        description=str(metadata["description"]),
        created_at=datetime.fromisoformat(created_at),
    )


def _mapping_from_event_metadata(
    metadata: dict,
    created_at: str,
) -> CoverageMapping:
    return CoverageMapping(
        mapping_id=str(metadata["mapping_id"]),
        target_id=str(metadata["target_id"]),
        evaluation_id=str(metadata["evaluation_id"]),
        evaluation_name=str(metadata["evaluation_name"]),
        evaluation_version=int(metadata["evaluation_version"]),
        created_at=datetime.fromisoformat(created_at),
    )


evaluation_coverage_service = EvaluationCoverageService()
