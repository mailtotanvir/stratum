from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SkillStep(BaseModel):
    instruction: str = Field(min_length=1)
    rationale: str | None = None


class SkillManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    skill_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: int = Field(ge=1)
    description: str = Field(min_length=1)
    methodology: str = Field(min_length=1)
    category: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    steps: list[SkillStep] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("skill_id", "name", "description", "methodology", "category")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class Skill(BaseModel):
    model_config = ConfigDict(frozen=True)

    manifest: SkillManifest
    source: str = Field(min_length=1)


class SkillRegistryEntry(BaseModel):
    skill_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: int = Field(ge=1)
    category: str = Field(min_length=1)
    source: str = Field(min_length=1)


class SkillRegistryCatalog(BaseModel):
    skills: list[SkillRegistryEntry]
    registered_skills_total: int = Field(ge=0)


class SkillRegistryDiagnostic(BaseModel):
    status: Literal["healthy", "degraded"]
    total_skills: int = Field(ge=0)
    duplicate_skill_ids: list[str] = Field(default_factory=list)
    invalid_skill_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

