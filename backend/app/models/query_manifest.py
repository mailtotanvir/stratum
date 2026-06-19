from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class QueryManifestCategory(BaseModel):
    category: str = Field(min_length=1)
    query_count: int = Field(ge=0)
    routes: list[str]


class QueryManifestEntry(BaseModel):
    query_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    projection_type: str = Field(min_length=1)
    category: str = Field(min_length=1)
    route: str
    supported_filters: list[str] = Field(default_factory=list)
    rebuildable: bool
    persisted: bool
    health_status: Literal["healthy", "unhealthy"]
    issues: list[str] = Field(default_factory=list)


class QueryManifest(BaseModel):
    schema_version: str = Field(min_length=1)
    generated_at: datetime
    health_status: Literal["healthy", "unhealthy"]
    query_count: int = Field(ge=0)
    categories: list[QueryManifestCategory]
    entries: list[QueryManifestEntry]
