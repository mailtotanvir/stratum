from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RuntimeQueryExecutionRequest(BaseModel):
    query_name: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    execution_context: dict[str, Any] = Field(default_factory=dict)
    requested_at: datetime


class RuntimeQueryExecutionDiagnostic(BaseModel):
    event_type: Literal[
        "runtime_query_execution_started",
        "runtime_query_execution_completed",
        "runtime_query_execution_failed",
    ]
    query_name: str
    execution_id: str
    duration_ms: float
    success: bool


class RuntimeQueryExecutionMetadata(BaseModel):
    query_name: str
    query_version: int
    handler_name: str
    execution_duration_ms: float


class RuntimeQueryExecutionResult(BaseModel):
    query_name: str
    execution_id: str
    executed_at: datetime
    success: bool
    result: Any = None
    diagnostics: list[RuntimeQueryExecutionDiagnostic]
    execution_metadata: RuntimeQueryExecutionMetadata


class RuntimeQueryExecutionInput(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    execution_context: dict[str, Any] = Field(default_factory=dict)
    requested_at: datetime | None = None


class RuntimeQueryParameterIssue(BaseModel):
    parameter: str
    error_type: Literal[
        "missing_parameter",
        "unknown_parameter",
        "invalid_parameter_type",
    ]
    message: str
    expected_type: str | None = None
    actual_type: str | None = None
