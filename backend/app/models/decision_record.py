from enum import StrEnum

from pydantic import BaseModel, Field


class DecisionType(StrEnum):
    RECOMMENDATION_SELECTION = "recommendation_selection"


class SelectedEntityType(StrEnum):
    PLANNER_RECOMMENDATION = "planner_recommendation"


class DecisionRecordCreate(BaseModel):
    decision_type: DecisionType
    selected_entity_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class DecisionRecord(BaseModel):
    decision_id: str
    session_id: str
    task_id: str
    decision_type: DecisionType
    selected_entity_id: str
    selected_entity_type: SelectedEntityType
    rationale: str
    created_at: str
