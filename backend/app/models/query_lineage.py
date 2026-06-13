from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.query_execution_record import QueryReconstructionInfo


class QueryLineage(BaseModel):
    execution_id: str = Field(min_length=1)
    query_name: str = Field(min_length=1)
    query_version: int = Field(ge=1)
    handler_name: str = Field(min_length=1)
    generated_at: datetime
    source_types: list[str]
    source_identifiers: dict[str, Any]
    source_counts: dict[str, int]
    reconstruction_info: QueryReconstructionInfo
    lineage_version: int = Field(default=1, ge=1)
