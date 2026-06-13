from datetime import datetime

from pydantic import BaseModel, Field


class QuerySnapshotManifest(BaseModel):
    execution_id: str = Field(min_length=1)
    query_name: str = Field(min_length=1)
    query_version: int = Field(ge=1)
    handler_name: str = Field(min_length=1)
    generated_at: datetime
    parameter_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    lineage_version: int = Field(ge=1)
    reconstruction_version: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
