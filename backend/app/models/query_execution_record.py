from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.runtime_query_execution import RuntimeQueryExecutionMetadata


class QueryExecutionRecord(BaseModel):
    execution_id: str = Field(min_length=1)
    query_name: str = Field(min_length=1)
    query_version: int = Field(ge=1)
    executed_at: datetime
    parameters: dict[str, Any] = Field(default_factory=dict)
    execution_metadata: RuntimeQueryExecutionMetadata
    success: bool
    result_summary: Any = None
    lineage_reference: dict[str, str] | None = None


class QueryReconstructionInfo(BaseModel):
    query_name: str = Field(min_length=1)
    query_version: int = Field(ge=1)
    handler_name: str = Field(min_length=1)
    execution_timestamp: datetime
    parameter_snapshot: dict[str, Any] = Field(default_factory=dict)
    reconstruction_version: int = Field(default=1, ge=1)


class QueryHistoryMetadata(BaseModel):
    record_count: int = Field(ge=0)
    reconstruction_version: int = Field(ge=1)


class QueryHistoryResponse(BaseModel):
    execution_records: list[QueryExecutionRecord]
    metadata: QueryHistoryMetadata
    reconstruction_information: list[QueryReconstructionInfo]


class QueryHistoryDetailResponse(BaseModel):
    execution_record: QueryExecutionRecord
    reconstruction_info: QueryReconstructionInfo
