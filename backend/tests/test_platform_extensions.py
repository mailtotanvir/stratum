from pathlib import Path

from app.sdk.diagnostics import build_extension_diagnostics
from app.sdk.loader import ExtensionLoader
from app.sdk.manifest import ExtensionManifest
from app.sdk.registry import extension_registry_service
from app.routes.platform import sdk_schema


def test_extension_manifest_validation() -> None:
    manifest = ExtensionManifest(
        extension_id="sample-extension",
        name="Sample Extension",
        version="1.0.0",
        author="Stratum",
        kind="provider",
        capabilities=["completion"],
        runtime_compatibility={"runtime": ">=1"},
        permissions=["network"],
        supported_protocols=["stratum-sdk"],
    )

    assert manifest.extension_id == "sample-extension"
    assert manifest.capabilities == ["completion"]


def test_extension_loader_discovers_sample_extensions(tmp_path: Path) -> None:
    root = tmp_path / "extensions"
    manifest_path = root / "sample" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        """
        {
          "extension_id": "sample",
          "name": "Sample",
          "version": "1.0.0",
          "author": "Stratum",
          "kind": "tool",
          "capabilities": ["analysis"],
          "runtime_compatibility": {"runtime": ">=1"},
          "dependencies": [],
          "permissions": [],
          "supported_protocols": ["stratum-sdk"],
          "enabled": true,
          "metadata": {}
        }
        """.strip(),
        encoding="utf-8",
    )

    loader = ExtensionLoader(root=root)
    extensions = loader.list_extensions()

    assert len(extensions) == 1
    assert extensions[0].manifest.extension_id == "sample"


def test_extension_diagnostics_report() -> None:
    loader = ExtensionLoader()
    report = build_extension_diagnostics(loader.list_extensions())

    assert report.installed_extensions >= 5
    assert report.disabled_extensions == 0
    assert report.dependency_issues == 0


def test_extension_registry_snapshot_and_schema_route() -> None:
    snapshot = extension_registry_service.snapshot()

    assert snapshot.total_extensions >= 5
    assert snapshot.enabled_extensions >= 5
    assert snapshot.contract_kinds["provider"] >= 1
    assert snapshot.contract_kinds["tool"] >= 1

    schema = sdk_schema()

    assert schema["contract"]["contract_id"] == "stratum.extension.sdk"
