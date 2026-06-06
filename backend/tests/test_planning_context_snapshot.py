from app.models.planning_context_snapshot import (
    PLANNING_CONTEXT_SNAPSHOT_VERSION,
    validate_planning_context_snapshot,
)


def test_current_planning_context_snapshot_is_valid() -> None:
    validation = validate_planning_context_snapshot(
        {"schema_version": PLANNING_CONTEXT_SNAPSHOT_VERSION}
    )

    assert validation == {
        "valid": True,
        "classification": "1",
        "schema_version": 1,
    }


def test_legacy_and_unknown_snapshot_versions_are_classified() -> None:
    assert validate_planning_context_snapshot({}) == {
        "valid": False,
        "classification": "legacy_or_unknown",
        "schema_version": None,
    }
    assert validate_planning_context_snapshot({"schema_version": 99}) == {
        "valid": False,
        "classification": "legacy_or_unknown",
        "schema_version": 99,
    }


def test_null_snapshot_is_valid_for_legacy_optional_fields() -> None:
    assert validate_planning_context_snapshot(None) == {
        "valid": True,
        "classification": "legacy_or_unknown",
        "schema_version": None,
    }
