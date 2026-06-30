from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.models.skill import (
    Skill,
    SkillManifest,
    SkillManifestDiagnostics,
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
            categories=sorted({skill.manifest.category for skill in self._skills.values()}),
            version_summary=self._version_summary(),
        )

    def diagnostics(self) -> SkillRegistryDiagnostic:
        invalid: list[str] = []
        missing_dependencies: list[str] = []
        registry = self._skills
        for skill in self._skills.values():
            try:
                SkillManifest.model_validate(skill.manifest.model_dump())
                for dependency in skill.manifest.dependencies:
                    if dependency.skill_id not in registry:
                        missing_dependencies.append(dependency.skill_id)
            except Exception:
                invalid.append(skill.manifest.skill_id)
        status = "degraded" if invalid or missing_dependencies else "healthy"
        warnings = []
        if invalid:
            warnings.append("Invalid skill definitions were detected.")
        if missing_dependencies:
            warnings.append("Missing skill dependencies were detected.")
        return SkillRegistryDiagnostic(
            status=status,
            total_skills=len(self._skills),
            duplicate_skill_ids=[],
            invalid_skill_ids=sorted(set(invalid)),
            missing_dependency_ids=sorted(set(missing_dependencies)),
            warnings=warnings,
        )

    def diagnostics_for(self, skill_id: str) -> SkillManifestDiagnostics:
        skill = self._skills[skill_id]
        warnings: list[str] = []
        if not skill.manifest.steps:
            warnings.append("Skill has no declared steps.")
        if not skill.manifest.methodology.strip():
            warnings.append("Skill has no declared methodology.")
        return SkillManifestDiagnostics(
            skill_id=skill_id,
            status="degraded" if warnings else "healthy",
            warnings=warnings,
            dependency_ids=[
                dependency.skill_id for dependency in skill.manifest.dependencies
            ],
            parameter_names=sorted(skill.manifest.parameters.keys()),
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
            dependency_count=len(skill.manifest.dependencies),
            parameter_count=len(skill.manifest.parameters),
        )

    def _version_summary(self) -> dict[str, int]:
        summary: dict[str, int] = {}
        for skill in self._skills.values():
            summary[skill.manifest.skill_id] = skill.manifest.version
        return summary


skill_registry_service = SkillRegistryService()
