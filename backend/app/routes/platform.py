from fastapi import APIRouter

from app.sdk.diagnostics import build_extension_diagnostics
from app.sdk.loader import ExtensionLoader

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/extensions")
def list_extensions() -> dict[str, object]:
    extensions = ExtensionLoader().list_extensions()
    return {
        "extensions": [
            {
                "manifest": ext.manifest.model_dump(mode="json"),
                "source_path": ext.source_path,
            }
            for ext in extensions
        ]
    }


@router.get("/diagnostics")
def platform_diagnostics() -> dict[str, object]:
    extensions = ExtensionLoader().list_extensions()
    report = build_extension_diagnostics(extensions)
    return {
        "installed_extensions": report.installed_extensions,
        "disabled_extensions": report.disabled_extensions,
        "incompatible_extensions": report.incompatible_extensions,
        "version_mismatches": report.version_mismatches,
        "dependency_issues": report.dependency_issues,
        "extensions": [
            {
                "extension_id": item.extension_id,
                "kind": item.kind,
                "status": item.status,
                "compatible": item.compatible,
                "dependency_issues": item.dependency_issues,
                "warnings": item.warnings,
                "source_path": item.source_path,
            }
            for item in report.extensions
        ],
    }
