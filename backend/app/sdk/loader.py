from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.sdk.manifest import ExtensionManifest


@dataclass(frozen=True)
class LoadedExtension:
    manifest: ExtensionManifest
    source_path: str


class ExtensionLoader:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path(__file__).resolve().parents[3] / ".stratum" / "extensions"

    def list_extensions(self) -> list[LoadedExtension]:
        if not self._root.exists():
            return []
        manifests = sorted(
            path for path in self._root.rglob("manifest.json") if path.is_file()
        )
        loaded = [self._load_manifest(path) for path in manifests]
        return sorted(loaded, key=lambda item: item.manifest.extension_id)

    def _load_manifest(self, manifest_path: Path) -> LoadedExtension:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return LoadedExtension(
            manifest=ExtensionManifest.model_validate(data),
            source_path=manifest_path.as_posix(),
        )
