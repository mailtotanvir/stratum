from datetime import datetime

from pydantic import BaseModel, Field


class QueryExecutorDispatchDiagnostic(BaseModel):
    query_id: str = Field(min_length=1)
    projection_type: str = Field(min_length=1)
    route: str
    executable: bool
    reason: str = Field(min_length=1)


class QueryExecutorDiagnostics(BaseModel):
    supported_query_count: int = Field(ge=0)
    catalog_query_count: int = Field(ge=0)
    executable_query_ids: list[str]
    unsupported_catalog_query_ids: list[str]
    missing_catalog_query_ids: list[str]
    generated_at: datetime
