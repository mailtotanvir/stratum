from datetime import datetime

from pydantic import BaseModel, Field


class DecisionPatternEntry(BaseModel):
    decision_key: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)
    occurrences: int = Field(ge=0)
    failures: int = Field(ge=0)
    rationale: str = Field(min_length=1)


class DecisionIntelligenceSummary(BaseModel):
    generated_at: datetime
    recurring_decisions: list[DecisionPatternEntry]
    repeated_failures: list[DecisionPatternEntry]
    evaluation_history: list[str]
    proposal_outcomes: list[str]
    engineering_rationale: list[str]

