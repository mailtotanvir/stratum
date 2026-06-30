from datetime import datetime

from pydantic import BaseModel, Field


class EngineeringKnowledgeEntry(BaseModel):
    knowledge_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    created_at: datetime


class EngineeringKnowledgeCatalog(BaseModel):
    generated_at: datetime
    entries: list[EngineeringKnowledgeEntry]

