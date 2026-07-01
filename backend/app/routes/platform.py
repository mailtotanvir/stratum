from fastapi import APIRouter

from app.sdk import export_sdk_schema
from app.sdk.diagnostics import build_extension_diagnostics
from app.sdk.loader import ExtensionLoader
from app.sdk.registry import extension_registry_service

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/extensions")
def list_extensions() -> dict[str, object]:
    snapshot = extension_registry_service.snapshot()
    return {
        "extensions": [
            {
                "manifest": ext.manifest.model_dump(mode="json"),
                "source_path": ext.source_path,
                "compatible": ext.compatible,
                "warnings": ext.warnings,
                "dependency_issues": ext.dependency_issues,
            }
            for ext in snapshot.entries
        ],
        "total_extensions": snapshot.total_extensions,
        "enabled_extensions": snapshot.enabled_extensions,
        "kinds": snapshot.kinds,
        "protocols": snapshot.protocols,
        "contract_kinds": snapshot.contract_kinds,
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


@router.get("/sdk/schema")
def sdk_schema() -> dict[str, object]:
    return export_sdk_schema()
