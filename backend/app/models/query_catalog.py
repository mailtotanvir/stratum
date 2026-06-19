from datetime import datetime

from pydantic import BaseModel, Field


class QueryCatalogEntry(BaseModel):
    query_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    projection_type: str = Field(min_length=1)
    route: str = Field(min_length=1)
    category: str = Field(min_length=1)
    filters: list[str] = Field(default_factory=list)
    rebuildable: bool
    persisted: bool


class QueryCatalog(BaseModel):
    entries: list[QueryCatalogEntry]
    generated_at: datetime
