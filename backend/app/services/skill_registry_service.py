from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.models.skill import (
    Skill,
    SkillManifest,
    SkillRegistryCatalog,
    SkillRegistryDiagnostic,
    SkillRegistryEntry,
)
from app.services.skill_loader_service import (
    SkillLoaderService,
    skill_loader_service,
)


class SkillRegistryError(ValueError):
    pass


class SkillRegistryService:
    def __init__(
        self,
        loader: SkillLoaderService | None = None,
        skills: Iterable[Skill | dict[str, Any]] | None = None,
    ) -> None:
        self._loader = loader or skill_loader_service
        self._skills: dict[str, Skill] = {}
        for skill in skills or self._loader.list_skill_manifests():
            self.register(skill)

    def register(self, skill: Skill | dict[str, Any]) -> SkillRegistryEntry:
        parsed = skill if isinstance(skill, Skill) else Skill.model_validate(skill)
        skill_id = parsed.manifest.skill_id
        if skill_id in self._skills:
            raise SkillRegistryError(f"Skill already registered: {skill_id}")
        self._skills[skill_id] = parsed
        return self._entry(parsed)

    def list_registry(self) -> SkillRegistryCatalog:
        return SkillRegistryCatalog(
            skills=[self._entry(skill) for skill in self._sorted_skills()],
            registered_skills_total=len(self._skills),
        )

    def diagnostics(self) -> SkillRegistryDiagnostic:
        invalid: list[str] = []
        for skill in self._skills.values():
            try:
                SkillManifest.model_validate(skill.manifest.model_dump())
            except Exception:
                invalid.append(skill.manifest.skill_id)
        status = "degraded" if invalid else "healthy"
        warnings = (
            ["Invalid skill definitions were detected."]
            if invalid
            else []
        )
        return SkillRegistryDiagnostic(
            status=status,
            total_skills=len(self._skills),
            duplicate_skill_ids=[],
            invalid_skill_ids=sorted(set(invalid)),
            warnings=warnings,
        )

    def _sorted_skills(self) -> list[Skill]:
        return sorted(
            self._skills.values(),
            key=lambda skill: (
                skill.manifest.category,
                skill.manifest.name,
                skill.manifest.skill_id,
            ),
        )

    def _entry(self, skill: Skill) -> SkillRegistryEntry:
        return SkillRegistryEntry(
            skill_id=skill.manifest.skill_id,
            name=skill.manifest.name,
            version=skill.manifest.version,
            category=skill.manifest.category,
            source=skill.source,
        )


skill_registry_service = SkillRegistryService()

