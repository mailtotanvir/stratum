from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.models.artifact import ArtifactKind
from app.models.proposal import ProposalSourceType
from app.models.runtime_event import EventType
from app.models.proposal import Proposal
from app.models.task import Task
from app.models.transformation_session import (
    TransformationSessionArtifact,
    TransformationSessionCreateRequest,
    TransformationSessionPatchProposal,
    TransformationSessionSummary,
)
from app.services.artifact_service import artifact_service
from app.services.event_service import EventService, event_service
from app.services.proposal_service import proposal_service
from app.services.repository_intelligence_service import repository_intelligence_service
from app.services.task_service import task_service
from app.services.trace_service import TraceService
from app.services.transformation_history_service import transformation_history_service


class TransformationSessionService:
    def __init__(
        self,
        tasks=None,
        proposals=None,
        artifacts=None,
        events=None,
        repository_intelligence=repository_intelligence_service,
    ) -> None:
        root = self._resolve_root(tasks=tasks, proposals=proposals, artifacts=artifacts)
        self._events = events or EventService(TraceService(root / "transformation_events.db"))
        self._tasks = self._clone_service(
            tasks,
            task_service.__class__,
            root / "transformation_tasks.db",
        )
        self._proposals = self._clone_service(
            proposals,
            proposal_service.__class__,
            root / "transformation_proposals.db",
        )
        self._artifacts = self._clone_service(
            artifacts,
            artifact_service.__class__,
            root / "transformation_artifacts.db",
        )
        self._repository_intelligence = repository_intelligence
        self._sessions: dict[str, TransformationSessionSummary] = {}

    def _resolve_root(self, *, tasks=None, proposals=None, artifacts=None) -> Path:
        for service in (tasks, proposals, artifacts):
            db_path = getattr(service, "_db_path", None)
            if db_path is not None:
                return Path(db_path).resolve().parent
        return Path(__file__).resolve().parents[3] / ".stratum"

    def _clone_service(self, service, service_cls, fallback_db_path: Path):
        db_path = getattr(service, "_db_path", None) if service is not None else None
        return service_cls(db_path or fallback_db_path, events=self._events)

    def create(self, request: TransformationSessionCreateRequest) -> TransformationSessionSummary:
        repository_summary = transformation_history_service.repository_change_summary()
        repository_intelligence = self._repository_intelligence.build()
        task = self._tasks.create_task(request.title)
        task = self._tasks.mark_running(task.id)
        transformation_id = f"transform-{uuid4().hex[:12]}"
        created_at = datetime.now(UTC)
        source_context_snapshot = {
            "objective": request.objective,
            "specification": request.specification,
            "context_markdown": request.context_markdown,
            "validation_command": request.validation_command,
            "affected_files": request.affected_files,
            "repository_summary": repository_summary.model_dump(mode="json"),
            "repository_intelligence": repository_intelligence.model_dump(mode="json"),
        }
        proposal = self._proposals.create_proposal(
            title=request.title,
            body=request.objective,
            task_id=task.id,
            source_type=ProposalSourceType.MANUAL.value,
            source_id=task.id,
            source_context_snapshot=source_context_snapshot,
        )
        self._events.emit_event_sync(
            EventType.PATCH_PROPOSED,
            f"Patch proposed for {request.title}",
            metadata={
                "transformation_id": transformation_id,
                "task_id": task.id,
                "proposal_id": proposal.id,
                "affected_files": request.affected_files,
                "validation_command": request.validation_command,
                "rollback_reference": repository_summary.rollback_reference,
            },
        )

        artifacts: list[TransformationSessionArtifact] = []
        artifacts.append(self._register_artifact(
            path=f"artifacts/{task.id}/specification.md",
            kind=ArtifactKind.SUMMARY.value,
            task_id=task.id,
            proposal_id=proposal.id,
            label="specification",
            content=request.specification,
            extra_metadata={"role": "specification"},
        ))
        if request.context_markdown:
            artifacts.append(self._register_artifact(
                path=f"artifacts/{task.id}/context.md",
                kind=ArtifactKind.SUMMARY.value,
                task_id=task.id,
                proposal_id=proposal.id,
                label="context",
                content=request.context_markdown,
                extra_metadata={"role": "context"},
            ))
        artifacts.append(self._register_artifact(
            path=f"artifacts/{task.id}/repository-summary.md",
            kind=ArtifactKind.REPORT.value,
            task_id=task.id,
            proposal_id=proposal.id,
            label="repository-summary",
            content=repository_summary.model_dump_json(indent=2),
            extra_metadata={"role": "repository_summary"},
        ))
        patch_artifact = self._register_artifact(
            path=f"artifacts/{task.id}/patch-proposal.patch",
            kind=ArtifactKind.PATCH.value,
            task_id=task.id,
            proposal_id=proposal.id,
            label="patch-proposal",
            content=self._build_patch_preview(request.affected_files),
            extra_metadata={
                "role": "patch_proposal",
                "validation_command": request.validation_command,
                "rollback_reference": repository_summary.rollback_reference,
                "affected_files": request.affected_files,
            },
        )
        artifacts.append(patch_artifact)
        summary = (
            f"Prepared {len(request.affected_files)} file targets with governed proposal and {len(artifacts)} artifacts."
        )
        task = self._tasks.mark_completed(task.id, summary=summary)
        record = TransformationSessionSummary(
            transformation_id=transformation_id,
            task=Task(
                id=task.id,
                status=task.status,
                title=task.title,
                created_at=task.created_at.isoformat(),
                completed_at=task.completed_at.isoformat() if task.completed_at else None,
                summary=task.summary,
            ),
            proposal=Proposal(
                id=proposal.id,
                task_id=proposal.task_id,
                source_type=proposal.source_type,
                source_id=proposal.source_id,
                source_context_snapshot=self._proposals.source_context_snapshot_for(proposal),
                title=proposal.title,
                body=proposal.body,
                status=proposal.status,
                created_at=proposal.created_at.isoformat(),
                resolved_at=proposal.resolved_at.isoformat() if proposal.resolved_at else None,
                decision=proposal.decision,
            ),
            repository_summary=repository_summary,
            repository_intelligence=repository_intelligence,
            artifacts=artifacts,
            patch=TransformationSessionPatchProposal(
                patch_id=transformation_id,
                status="proposed",
                validation_command=request.validation_command,
                rollback_reference=repository_summary.rollback_reference,
                affected_files=request.affected_files,
                proposal_id=proposal.id,
                artifact_id=patch_artifact.artifact_id,
                metadata={"requested_by": request.requested_by},
            ),
            history=transformation_history_service.history(),
            summary=summary,
            created_at=created_at,
            updated_at=created_at,
            validation_command=request.validation_command,
            checkpoint_commit=repository_summary.checkpoint_commit,
            rollback_reference=repository_summary.rollback_reference,
        )
        self._sessions[record.transformation_id] = record
        return record

    def list_sessions(self) -> list[TransformationSessionSummary]:
        return sorted(self._sessions.values(), key=lambda item: item.created_at, reverse=True)

    def get_session(self, transformation_id: str) -> TransformationSessionSummary:
        try:
            return self._sessions[transformation_id]
        except KeyError as exc:
            raise ValueError(f"Transformation session not found: {transformation_id}") from exc

    def _register_artifact(self, *, path: str, kind: str, task_id: str, proposal_id: str, label: str, content: str, extra_metadata: dict[str, object]) -> TransformationSessionArtifact:
        record = self._artifacts.create_artifact(
            path=path,
            kind=kind,
            task_id=task_id,
            proposal_id=proposal_id,
            metadata={"label": label, "content": content, **extra_metadata},
        )
        return TransformationSessionArtifact(
            artifact_id=record.id,
            path=record.path,
            kind=record.kind,
            label=label,
            created_at=record.created_at.isoformat(),
            metadata=self._artifacts.metadata_for(record) or {},
        )

    def _build_patch_preview(self, affected_files: list[str]) -> str:
        if not affected_files:
            return "# Patch proposal\n\nNo affected files were declared."
        return "# Patch proposal\n\n" + "\n".join(f"- {path}" for path in affected_files)


transformation_session_service = TransformationSessionService()
