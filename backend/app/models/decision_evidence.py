from enum import StrEnum

from pydantic import BaseModel, Field


class DecisionEvidenceType(StrEnum):
    RECOMMENDATION = "recommendation"
    PLANNING_CONTEXT_SNAPSHOT = "planning_context_snapshot"
    GOVERNANCE_PREVIEW = "governance_preview"


class DecisionEvidenceCreate(BaseModel):
    evidence_type: DecisionEvidenceType
    evidence_reference: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class DecisionEvidence(BaseModel):
    evidence_id: str
    decision_id: str
    evidence_type: DecisionEvidenceType
    evidence_reference: str
    summary: str
    created_at: str
