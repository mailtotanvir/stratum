from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from app.models.runtime_workspace_binding import (
    RuntimeWorkspaceBindingStatus,
    RuntimeWorkspaceRepositoryStatus,
)
from app.services.runtime_workspace_artifact_service import (
    RuntimeWorkspaceArtifactService,
    runtime_workspace_artifact_service,
)
from app.services.runtime_workspace_service import (
    RuntimeWorkspaceService,
    runtime_workspace_service,
)


class RuntimeWorkspaceBindingService:
    def __init__(
        self,
        workspace: RuntimeWorkspaceService | None = None,
        workspace_artifacts: RuntimeWorkspaceArtifactService | None = None,
    ) -> None:
        self._workspace = workspace or runtime_workspace_service
        self._workspace_artifacts = workspace_artifacts or runtime_workspace_artifact_service

    def get_binding_status(self) -> RuntimeWorkspaceBindingStatus:
        workspace = self._workspace.get_active_workspace()
        repository = self._repository_status(Path(workspace.root_path))
        workspace_artifacts = self._workspace_artifacts.list_workspace_artifacts(
            workspace.workspace_id
        )
        linked_session_ids = sorted(
            {
                artifact.session_id
                for artifact in workspace_artifacts
                if artifact.session_id is not None
            }
        )
        execution_allowed = repository.is_git_repository and (
            repository.safe_to_run or not repository.issues
        )
        reason = (
            "Workspace execution is allowed"
            if execution_allowed
            else "Workspace execution is blocked until repository checks pass"
        )
        return RuntimeWorkspaceBindingStatus(
            workspace=workspace.model_dump(mode="json"),
            repository=repository,
            workspace_artifact_count=len(workspace_artifacts),
            session_artifact_count=sum(
                1 for artifact in workspace_artifacts if artifact.session_id is not None
            ),
            linked_session_ids=linked_session_ids,
            runtime_execution_allowed=execution_allowed,
            runtime_execution_reason=reason,
            checked_at=datetime.now(UTC),
        )

    def _repository_status(self, workspace_root: Path) -> RuntimeWorkspaceRepositoryStatus:
        issues: list[str] = []
        metadata: dict[str, object] = {}
        try:
            top_level = _run_git(["rev-parse", "--show-toplevel"], workspace_root)
        except ValueError:
            return RuntimeWorkspaceRepositoryStatus(
                path=workspace_root.as_posix(),
                is_git_repository=False,
                safe_to_run=False,
                issues=["workspace_root_is_not_git_repository"],
            )
        repository_path = Path(top_level.stdout.strip()).resolve()
        branch = _run_git(["branch", "--show-current"], repository_path).stdout.strip() or "HEAD"
        head_commit = _run_git(["rev-parse", "HEAD"], repository_path).stdout.strip()
        status = _run_git(
            ["status", "--porcelain", "--", ".", ":(exclude).stratum"],
            repository_path,
        ).stdout.rstrip()
        dirty = bool(status.strip())
        if dirty:
            issues.append("repository_has_uncommitted_changes")
        return RuntimeWorkspaceRepositoryStatus(
            path=repository_path.as_posix(),
            is_git_repository=True,
            branch=branch,
            head_commit=head_commit,
            dirty=dirty,
            status=status or "clean",
            checkpoint_status="dirty" if dirty else "clean",
            safe_to_run=not dirty,
            issues=issues,
            metadata=metadata,
        )


def _run_git(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise ValueError(message or "git command failed")
    return result


runtime_workspace_binding_service = RuntimeWorkspaceBindingService()

