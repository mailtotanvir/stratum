from typing import Any


PLANNING_CONTEXT_SNAPSHOT_VERSION = 1
LEGACY_OR_UNKNOWN_SNAPSHOT_VERSION = "legacy_or_unknown"


def validate_planning_context_snapshot(
    snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    if snapshot is None:
        return {
            "valid": True,
            "classification": LEGACY_OR_UNKNOWN_SNAPSHOT_VERSION,
            "schema_version": None,
        }

    schema_version = snapshot.get("schema_version")
    if schema_version == PLANNING_CONTEXT_SNAPSHOT_VERSION:
        return {
            "valid": True,
            "classification": str(PLANNING_CONTEXT_SNAPSHOT_VERSION),
            "schema_version": schema_version,
        }

    return {
        "valid": False,
        "classification": LEGACY_OR_UNKNOWN_SNAPSHOT_VERSION,
        "schema_version": schema_version,
    }
