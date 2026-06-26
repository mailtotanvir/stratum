from typing import Any, Literal

from pydantic import BaseModel, Field


ProviderExecutionValidationSeverity = Literal["error", "warning", "info"]


class ProviderExecutionValidationIssue(BaseModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: ProviderExecutionValidationSeverity = "error"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderExecutionValidationResult(BaseModel):
    valid: bool
    issues: list[ProviderExecutionValidationIssue] = Field(
        default_factory=list
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
