from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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


class ProjectionMetadata(ProjectionSchemaInfo):
    built_at: datetime
    source: str = Field(min_length=1)


class Projection(BaseModel):
    metadata: ProjectionMetadata
