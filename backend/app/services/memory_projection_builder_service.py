from __future__ import annotations

from app.models.memory import RepositoryMemory, SessionMemory, WorkingMemory
from app.models.projection import ProjectionMetadata, ProjectionReconstructionInfo, ProjectionSchemaInfo
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.memory_reconstruction_service import memory_reconstruction_service


WORKING_MEMORY_PROJECTION_TYPE = "working_memory"
SESSION_MEMORY_PROJECTION_TYPE = "session_memory"
REPOSITORY_MEMORY_PROJECTION_TYPE = "repository_memory"
MEMORY_SCHEMA_VERSION = 1
MEMORY_SOURCE = "memory_reconstruction_service"


class WorkingMemoryProjectionBuilderService(
    BaseProjectionBuilder[str | None, WorkingMemory]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=WORKING_MEMORY_PROJECTION_TYPE,
        schema_version=MEMORY_SCHEMA_VERSION,
        builder_name="WorkingMemoryProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=WORKING_MEMORY_PROJECTION_TYPE,
            reconstruction_source="runtime_events_and_workspace_artifacts",
            authoritative_source="runtime_event_store",
        ),
    )
    projection_type = WORKING_MEMORY_PROJECTION_TYPE

    def build(self, source: str | None = None) -> WorkingMemory:
        return memory_reconstruction_service.reconstruct_working_memory(source)


class SessionMemoryProjectionBuilderService(
    BaseProjectionBuilder[str, SessionMemory]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=SESSION_MEMORY_PROJECTION_TYPE,
        schema_version=MEMORY_SCHEMA_VERSION,
        builder_name="SessionMemoryProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=SESSION_MEMORY_PROJECTION_TYPE,
            reconstruction_source="runtime_events_and_workspace_artifacts",
            authoritative_source="runtime_event_store",
        ),
    )
    projection_type = SESSION_MEMORY_PROJECTION_TYPE

    def build(self, source: str) -> SessionMemory:
        return memory_reconstruction_service.reconstruct_session_memory(source)


class RepositoryMemoryProjectionBuilderService(
    BaseProjectionBuilder[None, RepositoryMemory]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=REPOSITORY_MEMORY_PROJECTION_TYPE,
        schema_version=MEMORY_SCHEMA_VERSION,
        builder_name="RepositoryMemoryProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=REPOSITORY_MEMORY_PROJECTION_TYPE,
            reconstruction_source="runtime_events_artifacts_and_sessions",
            authoritative_source="runtime_event_store",
        ),
    )
    projection_type = REPOSITORY_MEMORY_PROJECTION_TYPE

    def build(self, source: None = None) -> RepositoryMemory:
        return memory_reconstruction_service.reconstruct_repository_memory()


working_memory_projection_builder_service = WorkingMemoryProjectionBuilderService()
session_memory_projection_builder_service = SessionMemoryProjectionBuilderService()
repository_memory_projection_builder_service = RepositoryMemoryProjectionBuilderService()
