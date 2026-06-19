from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class QueryHealthEntry(BaseModel):
    query_id: str = Field(min_length=1)
    projection_type: str = Field(min_length=1)
    route: str
    status: Literal["healthy", "unhealthy"]
    issues: list[str] = Field(default_factory=list)


class QueryHealth(BaseModel):
    query_surface_count: int = Field(ge=0)
    registered_projection_count: int = Field(ge=0)
    missing_route_count: int = Field(ge=0)
    missing_filter_metadata_count: int = Field(ge=0)
    duplicate_route_count: int = Field(ge=0)
    unhealthy_entries: list[QueryHealthEntry]
    generated_at: datetime
