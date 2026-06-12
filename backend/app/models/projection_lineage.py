from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProjectionLineage(BaseModel):
    projection_name: str = Field(min_length=1)
    builder_name: str = Field(min_length=1)
    schema_version: int = Field(ge=1)
    generated_at: datetime
    reconstruction_info: dict[str, Any]
    source_types: list[str]
    source_identifiers: dict[str, Any]
    source_counts: dict[str, int]
    lineage_version: int = Field(default=1, ge=1)
