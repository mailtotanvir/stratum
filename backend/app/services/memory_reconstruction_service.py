from __future__ import annotations

from datetime import UTC, datetime

from app.models.memory import (
    ArtifactMemory,
    DecisionMemory,
    MemoryDiagnostics,
    MemorySourceSummary,
    RepositoryMemory,
    SessionMemory,
    WorkingMemory,
)
from app.services.artifact_service import ArtifactService, artifact_service
from app.services.event_service import EventService, event_service
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)
from app.services.runtime_workspace_artifact_service import (
    RuntimeWorkspaceArtifactService,
    runtime_workspace_artifact_service,
)
from app.services.runtime_workspace_service import (
    RuntimeWorkspaceService,
    runtime_workspace_service,
)
from app.services.skill_registry_service import (
    SkillRegistryService,
    skill_registry_service,
)


class MemoryReconstructionService:
    def __init__(
        self,
        events: EventService | None = None,
        sessions: RuntimeSessionService | None = None,
        workspace: RuntimeWorkspaceService | None = None,
        workspace_artifacts: RuntimeWorkspaceArtifactService | None = None,
        skills: SkillRegistryService | None = None,
        artifacts: ArtifactService | None = None,
    ) -> None:
        self._events = events or event_service
        self._sessions = sessions or runtime_session_service
        self._workspace = workspace or runtime_workspace_service
        self._workspace_artifacts = (
            workspace_artifacts or runtime_workspace_artifact_service
        )
        self._skills = skills or skill_registry_service
        self._artifacts = artifacts or artifact_service

    def reconstruct_artifact_memory(self) -> list[ArtifactMemory]:
        return [
            ArtifactMemory(
                artifact_id=artifact.id,
                summary=artifact.path,
                created_at=artifact.created_at,
                artifact_type=artifact.kind,
                metadata=artifact.metadata or {},
            )
            for artifact in self._artifacts.list_artifacts()
        ]

    def reconstruct_decision_memory(self) -> list[DecisionMemory]:
        records = []
        for event in self._events.list_persisted_events():
            if "decision_id" not in event.metadata:
                continue
            records.append(
                DecisionMemory(
                    decision_id=str(event.metadata["decision_id"]),
                    rationale=str(event.metadata.get("rationale") or event.message),
                    evidence=[str(event.metadata.get("evidence_id"))]
                    if event.metadata.get("evidence_id")
                    else [],
                    alternatives=[
                        str(event.metadata["alternative"])
                    ]
                    if event.metadata.get("alternative")
                    else [],
                    outcome=str(event.metadata.get("outcome") or event.type.value),
                    session_id=event.metadata.get("session_id"),
                    repeated_count=sum(
                        1
                        for candidate in self._events.list_persisted_events()
                        if candidate.metadata.get("decision_id")
                        == event.metadata["decision_id"]
                    ),
                )
            )
        return records

    def reconstruct_working_memory(
        self, session_id: str | None = None
    ) -> WorkingMemory:
        events = self._events.list_persisted_events()
        latest = events[-1] if events else None
        session = (
            self._sessions.get_session(session_id)
            if session_id is not None
            else None
        )
        artifacts = (
            self._workspace_artifacts.list_session_artifacts(session_id)
            if session_id
            else []
        )
        active_skill_ids = [
            item.skill_id for item in self._skills.list_registry().skills
        ]
        return WorkingMemory(
            session_id=session_id,
            task_id=session.task_id if session is not None else None,
            latest_event_id=latest.id if latest else None,
            latest_event_type=latest.type.value if latest else None,
            active_skill_ids=active_skill_ids,
            recent_artifact_ids=[artifact.artifact_id for artifact in artifacts[:5]],
            summary=_working_summary(
                session_id,
                latest.type.value if latest else None,
                len(artifacts),
                len(active_skill_ids),
            ),
        )

    def reconstruct_session_memory(self, session_id: str) -> SessionMemory:
        session = self._sessions.get_session(session_id)
        events = [
            event
            for event in self._events.list_persisted_events()
            if event.metadata.get("session_id") == session_id
            or event.metadata.get("runtime_session_id") == session_id
        ]
        workspace_artifacts = self._workspace_artifacts.list_session_artifacts(
            session_id
        )
        active_skill_ids = [
            item.skill_id for item in self._skills.list_registry().skills
        ]
        return SessionMemory(
            session_id=session.id,
            task_id=session.task_id,
            status=session.status,
            event_count=len(events),
            artifact_ids=[artifact.artifact_id for artifact in workspace_artifacts],
            skill_ids=active_skill_ids,
            last_activity_at=events[-1].ts if events else session.created_at,
            summary=_session_summary(
                session.id,
                session.status,
                len(events),
                len(workspace_artifacts),
                len(active_skill_ids),
            ),
        )

    def reconstruct_repository_memory(self) -> RepositoryMemory:
        sessions = self._sessions.list_sessions()
        session_memories = [
            self.reconstruct_session_memory(session.id) for session in sessions
        ]
        artifacts = self._artifacts.list_artifacts()
        generated_at = datetime.now(UTC)
        skill_ids = [item.skill_id for item in self._skills.list_registry().skills]
        return RepositoryMemory(
            repository_id=self._workspace.configuration.workspace_id,
            generated_at=generated_at,
            source_summary=MemorySourceSummary(
                event_count=len(self._events.list_persisted_events()),
                artifact_count=len(artifacts),
                workspace_artifact_count=len(
                    self._workspace_artifacts.list_workspace_artifacts(
                        self._workspace.configuration.workspace_id
                    )
                ),
                session_count=len(sessions),
            ),
            session_memories=session_memories,
            skill_ids=skill_ids,
            artifact_ids=[artifact.id for artifact in artifacts],
            summary=_repository_summary(
                len(session_memories), len(skill_ids), len(artifacts)
            ),
        )

    def diagnostics(self) -> MemoryDiagnostics:
        source_summary = MemorySourceSummary(
            event_count=len(self._events.list_persisted_events()),
            artifact_count=len(self._artifacts.list_artifacts()),
            workspace_artifact_count=len(
                self._workspace_artifacts.list_workspace_artifacts(
                    self._workspace.configuration.workspace_id
                )
            ),
            session_count=len(self._sessions.list_sessions()),
        )
        return MemoryDiagnostics(
            status="healthy",
            source_summary=source_summary,
            working_memory_count=1,
            session_memory_count=source_summary.session_count,
            repository_memory_count=1,
            artifact_memory_count=len(self.reconstruct_artifact_memory()),
            decision_memory_count=len(self.reconstruct_decision_memory()),
            warnings=[],
            build_timestamp=datetime.now(UTC),
        )


def _working_summary(
    session_id: str | None,
    latest_event_type: str | None,
    artifact_count: int,
    skill_count: int,
) -> str:
    return (
        f"Working memory for {session_id or 'repository'}: "
        f"{artifact_count} artifacts, {skill_count} skills, "
        f"latest event {latest_event_type or 'none'}"
    )


def _session_summary(
    session_id: str,
    status: str,
    event_count: int,
    artifact_count: int,
    skill_count: int,
) -> str:
    return (
        f"Session {session_id} is {status} with {event_count} events, "
        f"{artifact_count} artifacts, {skill_count} skills"
    )


def _repository_summary(session_count: int, skill_count: int, artifact_count: int) -> str:
    return (
        f"Repository memory spans {session_count} sessions, "
        f"{artifact_count} artifacts, {skill_count} skills"
    )


memory_reconstruction_service = MemoryReconstructionService()
