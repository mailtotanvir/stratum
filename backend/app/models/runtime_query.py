from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


RuntimeQueryType = Literal[
    "projection_query",
    "session_query",
    "decision_query",
    "diagnostic_query",
]


class RuntimeQuery(BaseModel):
    query_name: str = Field(min_length=1)
    query_version: int = Field(ge=1)
    description: str = Field(min_length=1)
    query_type: RuntimeQueryType
    supported_parameters: dict[str, Any]
    result_schema: dict[str, Any]


class RuntimeQueryDiagnostic(BaseModel):
    event_type: Literal[
        "runtime_query_registered",
        "runtime_query_discovered",
        "runtime_query_executed",
    ]
    query_name: str
    query_version: int
    handler: str


class RuntimeQueryResult(BaseModel):
    query_name: str
    executed_at: datetime
    result: Any
    diagnostics: list[RuntimeQueryDiagnostic]
    query_metadata: RuntimeQuery


class RuntimeQueryDiscovery(BaseModel):
    queries: list[RuntimeQuery]
