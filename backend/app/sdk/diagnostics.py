from __future__ import annotations

from dataclasses import dataclass, field

from app.sdk.loader import LoadedExtension


@dataclass(frozen=True)
class ExtensionDiagnostic:
    extension_id: str
    kind: str
    status: str
    compatible: bool
    dependency_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_path: str = ""


@dataclass(frozen=True)
class ExtensionDiagnosticsReport:
    extensions: list[ExtensionDiagnostic]
    installed_extensions: int
    disabled_extensions: int
    incompatible_extensions: int
    version_mismatches: int
    dependency_issues: int


def build_extension_diagnostics(extensions: list[LoadedExtension]) -> ExtensionDiagnosticsReport:
    diagnostics: list[ExtensionDiagnostic] = []
    installed = len(extensions)
    disabled = 0
    incompatible = 0
    dependency_issues = 0
    by_id = {ext.manifest.extension_id: ext.manifest.version for ext in extensions}
    for ext in extensions:
        manifest = ext.manifest
        issues: list[str] = []
        if not manifest.enabled:
            disabled += 1
        runtime = manifest.runtime_compatibility
        if runtime.get("runtime") not in (None, ">=1"):
            incompatible += 1
        for dep in manifest.dependencies:
            if dep.extension_id not in by_id:
                issues.append(f"missing dependency: {dep.extension_id}")
            elif by_id[dep.extension_id] < dep.minimum_version:
                issues.append(
                    f"version mismatch: {dep.extension_id} requires {dep.minimum_version}"
                )
        if issues:
            dependency_issues += 1
        diagnostics.append(
            ExtensionDiagnostic(
                extension_id=manifest.extension_id,
                kind=manifest.kind,
                status="disabled" if not manifest.enabled else ("degraded" if issues else "healthy"),
                compatible=not runtime.get("runtime") or runtime.get("runtime") == ">=1",
                dependency_issues=issues,
                warnings=[],
                source_path=ext.source_path,
            )
        )
    return ExtensionDiagnosticsReport(
        extensions=diagnostics,
        installed_extensions=installed,
        disabled_extensions=disabled,
        incompatible_extensions=incompatible,
        version_mismatches=dependency_issues,
        dependency_issues=dependency_issues,
    )
