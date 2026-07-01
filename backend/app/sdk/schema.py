from __future__ import annotations

from typing import Any

from app.sdk.contracts import ContractSchema
from app.sdk.manifest import ExtensionManifest


def export_sdk_schema() -> dict[str, Any]:
    return {
        "contract": ContractSchema(
            contract_id="stratum.extension.sdk",
            version="1.0.0",
            description="Stable extension SDK schema exports for Stratum v1.",
            metadata={
                "contracts": [
                    "provider",
                    "tool",
                    "execution-participant",
                    "agent-adapter",
                    "skill",
                    "evaluation-pack",
                ]
            },
        ).model_dump(mode="json"),
        "extension_manifest": ExtensionManifest.model_json_schema(),
    }
