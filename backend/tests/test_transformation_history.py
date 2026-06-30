from types import SimpleNamespace

from app.models.runtime_event import EventType
from app.services.artifact_service import artifact_service
from app.services.event_service import event_service
from app.services.transformation_history_service import transformation_history_service


def test_transformation_history_projects_artifacts_and_patches(monkeypatch) -> None:
    artifact_service.create_artifact_without_event(
        path="artifacts/task-1/report.md",
        kind="report",
        task_id="task-1",
        metadata={
            "session_id": "session-1",
            "workspace_id": "workspace-1",
            "producer": "tool:reporter",
            "checksum": "abc123",
        },
    )
    event_service.emit_event_sync(
        EventType.PATCH_APPLIED,
        "Applied patch",
        metadata={
            "patch_id": "patch-1",
            "session_id": "session-1",
            "proposal_id": "proposal-1",
            "artifact_id": "art-1",
            "affected_files": ["backend/app/main.py"],
            "validation_result": "passed",
            "rollback_reference": "commit-123",
        },
    )

    monkeypatch.setattr(
        "app.services.transformation_history_service._run_git",
        lambda root, args: " M backend/app/main.py\n?? new-file.txt\n"
        if args == ["status", "--short"]
        else "main",
    )

    artifacts = transformation_history_service.artifacts()
    patches = transformation_history_service.patches()
    summary = transformation_history_service.repository_change_summary()
    history = transformation_history_service.history()

    assert artifacts[0].path == "artifacts/task-1/report.md"
    assert artifacts[0].producer == "tool:reporter"
    assert artifacts[0].checksum == "abc123"
    assert patches[0].id == "patch-1"
    assert patches[0].status == "applied"
    assert summary.dirty_workspace is True
    assert "backend/app/main.py" in summary.modified_files
    assert history.summary.total_events >= 1
    assert any(item.stage == "patch" for item in history.items)

