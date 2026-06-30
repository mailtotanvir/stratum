from __future__ import annotations

import json
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.artifact import ArtifactKind
from app.models.transformation_history import (
    ArtifactRecordView,
    PatchRecordView,
    RepositoryChangeSummary,
    TransformationHistoryItem,
    TransformationHistoryProjection,
    TransformationHistorySummary,
)
from app.services.artifact_service import artifact_service
from app.services.event_service import event_service
from app.services.runtime_workspace_service import runtime_workspace_service


class TransformationHistoryService:
    def artifacts(self) -> list[ArtifactRecordView]:
        items: list[ArtifactRecordView] = []
        for record in artifact_service.list_artifacts():
            metadata = artifact_service.metadata_for(record) or {}
            items.append(
                ArtifactRecordView(
                    id=record.id,
                    type=record.kind,
                    path=record.path,
                    origin_event_id=_int_or_none(metadata.get("origin_event_id")),
                    session_id=record.task_id or _string_or_none(metadata.get("session_id")),
                    workspace_id=_string_or_none(metadata.get("workspace_id")),
                    producer=_string_or_none(metadata.get("producer")),
                    status=_string_or_none(metadata.get("status")) or "created",
                    metadata=metadata,
                    checksum=_string_or_none(metadata.get("checksum")),
                )
            )
        return items

    def patches(self) -> list[PatchRecordView]:
        events = event_service.list_persisted_events()
        artifacts = {artifact.id: artifact for artifact in artifact_service.list_artifacts()}
        items: list[PatchRecordView] = []
        for event in events:
            if not event.type.startswith("patch_"):
                continue
            metadata = dict(event.metadata)
            patch_id = _string_or_none(metadata.get("patch_id")) or f"patch-event-{event.id}"
            items.append(
                PatchRecordView(
                    id=patch_id,
                    session_id=_string_or_none(metadata.get("session_id")),
                    proposal_id=_string_or_none(metadata.get("proposal_id")),
                    artifact_id=_string_or_none(metadata.get("artifact_id")),
                    status=event.type.removeprefix("patch_"),
                    affected_files=_string_list(metadata.get("affected_files")),
                    origin_event_id=event.id,
                    approval_event_id=_int_or_none(metadata.get("approval_event_id")),
                    validation_result=_string_or_none(metadata.get("validation_result")),
                    rollback_reference=_string_or_none(metadata.get("rollback_reference")),
                    metadata={
                        **metadata,
                        "message": event.message,
                        "artifact_exists": _string_or_none(metadata.get("artifact_id")) in artifacts,
                    },
                )
            )
        return items

    def repository_change_summary(self) -> RepositoryChangeSummary:
        workspace = runtime_workspace_service.configuration
        root = Path(workspace.root_path)
        summary = RepositoryChangeSummary(
            workspace_id=workspace.workspace_id,
            path=str(root),
            repository_detected=False,
            status="unknown",
            metadata={"workspace_name": workspace.name},
        )
        if not (root / ".git").exists():
            summary.warnings.append("workspace_is_not_a_git_repository")
            return summary
        summary.repository_detected = True
        summary.branch = _run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip() or None
        summary.head_commit = _run_git(root, ["rev-parse", "HEAD"]).strip() or None
        status = _run_git(root, ["status", "--short"]).splitlines()
        summary.git_status = status
        summary.dirty_workspace = bool(status)
        summary.modified_files = [line[3:] for line in status if line.startswith((" M", "M "))]
        summary.added_files = [line[3:] for line in status if line.startswith(("A ", "??"))]
        summary.deleted_files = [line[3:] for line in status if line.startswith(("D ", " D"))]
        if status:
            summary.diff_summaries = _run_git(root, ["diff", "--stat"]).splitlines()
            summary.status = "dirty"
            summary.warnings.append("uncommitted_changes_present")
        else:
            summary.status = "clean"
        checkpoint = _run_git(root, ["rev-parse", "HEAD"]).strip()
        summary.checkpoint_commit = checkpoint or None
        summary.rollback_reference = checkpoint or None
        return summary

    def history(self) -> TransformationHistoryProjection:
        events = event_service.list_persisted_events()
        items: list[TransformationHistoryItem] = []
        for event in events:
            metadata = dict(event.metadata)
            stage = _stage_for_event(event.type)
            if stage is None:
                continue
            items.append(
                TransformationHistoryItem(
                    timestamp=event.ts,
                    session_id=_string_or_none(metadata.get("session_id")),
                    task_id=_string_or_none(metadata.get("task_id")),
                    proposal_id=_string_or_none(metadata.get("proposal_id")),
                    patch_id=_string_or_none(metadata.get("patch_id")),
                    artifact_id=_string_or_none(metadata.get("artifact_id")),
                    event_id=event.id,
                    stage=stage,
                    status=event.type,
                    summary=event.message,
                    metadata=metadata,
                )
            )
        items.sort(key=lambda item: (item.timestamp, item.event_id or 0))
        patterns = Counter(item.stage for item in items)
        failed = sum(1 for item in items if "failed" in item.status or "rejected" in item.status)
        sessions = {item.session_id for item in items if item.session_id}
        return TransformationHistoryProjection(
            items=items,
            summary=TransformationHistorySummary(
                total_events=len(items),
                repeated_patterns=[
                    f"{stage}:{count}"
                    for stage, count in patterns.items()
                    if count > 1
                ],
                failed_attempts=failed,
                sessions_with_transformations=len(sessions),
            ),
        )


def _stage_for_event(event_type: Any) -> str | None:
    value = str(event_type)
    if value.startswith("patch_"):
        return "patch"
    if value in {"artifact_created", "runtime_artifact_attached", "proposal_artifact_attached"}:
        return "artifact"
    if value in {"proposal_generated", "proposal_resolved", "approval_requested"}:
        return "proposal"
    if value in {"tool_execution_completed", "tool_execution_failed", "tool_result"}:
        return "validation"
    if value in {"runtime_session_created", "runtime_session_completed", "runtime_task_started"}:
        return "task"
    return None


def _run_git(root: Path, args: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()
    except Exception:
        return ""


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


transformation_history_service = TransformationHistoryService()

