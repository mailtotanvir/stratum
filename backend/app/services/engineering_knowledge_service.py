from __future__ import annotations

from datetime import UTC, datetime

from app.models.engineering_knowledge import (
    EngineeringKnowledgeCatalog,
    EngineeringKnowledgeEntry,
)
from app.services.artifact_service import artifact_service
from app.services.skill_registry_service import skill_registry_service


class EngineeringKnowledgeService:
    def build(self) -> EngineeringKnowledgeCatalog:
        skills = skill_registry_service.list_registry().skills
        artifacts = artifact_service.list_artifacts()
        entries = [
            EngineeringKnowledgeEntry(
                knowledge_id=f"skill:{skill.skill_id}",
                category="skill",
                title=skill.name,
                summary=f"Reusable methodology for {skill.category} work.",
                evidence=[skill.source],
                created_at=datetime.now(UTC),
            )
            for skill in skills
        ]
        entries.extend(
            EngineeringKnowledgeEntry(
                knowledge_id=f"artifact:{artifact.id}",
                category="artifact",
                title=artifact.path,
                summary=artifact.kind,
                evidence=[artifact.path],
                created_at=artifact.created_at,
            )
            for artifact in artifacts[:10]
        )
        return EngineeringKnowledgeCatalog(
            generated_at=datetime.now(UTC),
            entries=entries,
        )


engineering_knowledge_service = EngineeringKnowledgeService()

