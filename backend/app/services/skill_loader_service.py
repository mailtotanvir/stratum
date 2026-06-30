from __future__ import annotations

import json
from pathlib import Path

from app.models.skill import Skill, SkillManifest


class SkillLoaderService:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path(__file__).resolve().parents[2] / "skills"

    def list_skill_manifests(self) -> list[Skill]:
        if not self._root.exists():
            return []
        paths = sorted(self._root.rglob("skill.json"))
        return [self._load_manifest(path) for path in paths]

    def _load_manifest(self, manifest_path: Path) -> Skill:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return Skill(
            manifest=SkillManifest.model_validate(data),
            source=manifest_path.as_posix(),
        )


skill_loader_service = SkillLoaderService()
