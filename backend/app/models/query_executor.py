from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class QueryExecutionRequest(BaseModel):
    query_id: str = Field(min_length=1)
    filters: dict[str, Any] = Field(default_factory=dict)


class QueryExecutionResult(BaseModel):
    query_id: str = Field(min_length=1)
    projection_type: str = Field(min_length=1)
    route: str = Field(min_length=1)
    executed_at: datetime
    result: Any
