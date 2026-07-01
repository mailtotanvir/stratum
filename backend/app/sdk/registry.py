from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.sdk.contracts import PUBLIC_CONTRACT_NAMES
from app.sdk.loader import ExtensionLoader, LoadedExtension
from app.sdk.manifest import ExtensionManifest


@dataclass(frozen=True)
class ExtensionRegistryEntry:
    manifest: ExtensionManifest
    source_path: str
    compatible: bool
    warnings: list[str] = field(default_factory=list)
    dependency_issues: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExtensionRegistrySnapshot:
    entries: list[ExtensionRegistryEntry]
    total_extensions: int
    enabled_extensions: int
    kinds: dict[str, int]
    protocols: dict[str, int]
    contract_kinds: dict[str, int]


class ExtensionRegistryService:
    def __init__(self, loader: ExtensionLoader | None = None) -> None:
        self._loader = loader or ExtensionLoader()

    def list_extensions(self) -> list[LoadedExtension]:
        return self._loader.list_extensions()

    def snapshot(self) -> ExtensionRegistrySnapshot:
        extensions = self.list_extensions()
        entries: list[ExtensionRegistryEntry] = []
        kinds: dict[str, int] = {}
        protocols: dict[str, int] = {}
        contract_kinds: dict[str, int] = {}
        by_id = {ext.manifest.extension_id: ext.manifest for ext in extensions}

        for ext in extensions:
            manifest = ext.manifest
            warnings: list[str] = []
            dependency_issues: list[str] = []
            compatible = _is_runtime_compatible(manifest.runtime_compatibility)
            if not compatible:
                warnings.append("runtime contract mismatch")
            contract_name = manifest.target_contract()
            if contract_name not in PUBLIC_CONTRACT_NAMES:
                warnings.append(f"unknown target contract: {contract_name}")
            for dep in manifest.dependencies:
                dep_manifest = by_id.get(dep.extension_id)
                if dep_manifest is None:
                    dependency_issues.append(f"missing dependency: {dep.extension_id}")
                elif _compare_versions(dep_manifest.version, dep.minimum_version) < 0:
                    dependency_issues.append(
                        f"version mismatch: {dep.extension_id} requires {dep.minimum_version}"
                    )
            if manifest.enabled:
                kinds[manifest.kind] = kinds.get(manifest.kind, 0) + 1
                contract_kinds[contract_name] = contract_kinds.get(contract_name, 0) + 1
                for protocol in manifest.supported_protocols:
                    protocols[protocol] = protocols.get(protocol, 0) + 1
            entries.append(
                ExtensionRegistryEntry(
                    manifest=manifest,
                    source_path=ext.source_path,
                    compatible=compatible,
                    warnings=warnings,
                    dependency_issues=dependency_issues,
                )
            )

        return ExtensionRegistrySnapshot(
            entries=entries,
            total_extensions=len(entries),
            enabled_extensions=sum(1 for ext in extensions if ext.manifest.enabled),
            kinds=dict(sorted(kinds.items())),
            protocols=dict(sorted(protocols.items())),
            contract_kinds=dict(sorted(contract_kinds.items())),
        )


def _is_runtime_compatible(runtime_compatibility: dict[str, Any]) -> bool:
    runtime = runtime_compatibility.get("runtime")
    return runtime in (None, "", ">=1", ">=1.0")


def _compare_versions(left: str, right: str) -> int:
    def parse(value: str) -> tuple[int, ...]:
        parts: list[int] = []
        for chunk in value.split("."):
            digits = "".join(character for character in chunk if character.isdigit())
            parts.append(int(digits) if digits else 0)
        return tuple(parts)

    left_parts = parse(left)
    right_parts = parse(right)
    width = max(len(left_parts), len(right_parts))
    left_parts = left_parts + (0,) * (width - len(left_parts))
    right_parts = right_parts + (0,) * (width - len(right_parts))
    if left_parts < right_parts:
        return -1
    if left_parts > right_parts:
        return 1
    return 0


extension_registry_service = ExtensionRegistryService()
