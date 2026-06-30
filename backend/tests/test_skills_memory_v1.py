from datetime import UTC, datetime
from pathlib import Path

import app.routes.memory as memory_routes
import app.routes.skills as skills_routes
import app.routes.diagnostics as diagnostics_routes
from app.models.memory import RepositoryMemory, SessionMemory, WorkingMemory
from app.models.skill import SkillManifest, SkillStep
from app.runtime.projection_registry import projection_registry
from app.services.event_service import EventService
from app.services.artifact_service import ArtifactService
from app.services.memory_reconstruction_service import MemoryReconstructionService
from app.services.skill_loader_service import SkillLoaderService
from app.services.skill_registry_service import SkillRegistryService
from app.services.trace_service import TraceService
from app.services.runtime_session_service import RuntimeSessionService
from app.services.runtime_workspace_artifact_service import RuntimeWorkspaceArtifactService
from app.services.runtime_workspace_service import RuntimeWorkspaceService


NOW = datetime(2026, 6, 15, 18, 0, tzinfo=UTC)


def test_skill_manifest_validation() -> None:
    manifest = SkillManifest(
        skill_id="skill-code-review",
        name="Code Review",
        version=1,
        description="Deterministic review methodology",
        methodology="Inspect, verify, report",
        category="engineering",
        tags=["review", "backend"],
        steps=[SkillStep(instruction="Inspect runtime events.")],
    )

    assert manifest.skill_id == "skill-code-review"
    assert manifest.steps[0].instruction == "Inspect runtime events."


def test_skill_registry_is_sorted_and_declarative(tmp_path) -> None:
    loader = SkillLoaderService(tmp_path / "missing-skills")
    registry = SkillRegistryService(loader=loader)
    registry.register(
        {
            "manifest": {
                "skill_id": "skill-b",
                "name": "B",
                "version": 1,
                "description": "b",
                "methodology": "deterministic",
                "category": "beta",
                "steps": [],
                "tags": [],
                "metadata": {},
            },
            "source": "tests/b.json",
        }
    )
    registry.register(
        {
            "manifest": {
                "skill_id": "skill-a",
                "name": "A",
                "version": 1,
                "description": "a",
                "methodology": "deterministic",
                "category": "alpha",
                "steps": [],
                "tags": [],
                "metadata": {},
            },
            "source": "tests/a.json",
        }
    )

    assert [item.skill_id for item in registry.list_registry().skills] == [
        "skill-a",
        "skill-b",
    ]
    assert registry.diagnostics().status == "healthy"


def make_services(tmp_path: Path):
    events = EventService(TraceService(tmp_path / "memory.db"))
    artifacts = ArtifactService(tmp_path / "artifacts.db")
    sessions = RuntimeSessionService(tmp_path / "sessions.db")
    workspace = RuntimeWorkspaceService(tmp_path)
    workspace_artifacts = RuntimeWorkspaceArtifactService(workspace)
    session = sessions.create_session("task-1")
    events.emit_event_sync(
        "runtime_session_created",
        "Session created",
        metadata={"runtime_session_id": session.id, "task_id": session.task_id},
    )
    events.emit_event_sync(
        "tool_execution_completed",
        "Tool completed",
        metadata={"session_id": session.id, "tool_invocation_id": "tool-1"},
    )
    workspace_artifacts.record_artifact(
        workspace_id=workspace.configuration.workspace_id,
        tool="writer",
        artifact_type="note",
        summary="Session note",
        session_id=session.id,
        path="notes/session.md",
        metadata={"kind": "note"},
        artifact_id="artifact-1",
        created_at=NOW,
    )
    registry = SkillRegistryService()
    return MemoryReconstructionService(
        events=events,
        sessions=sessions,
        workspace=workspace,
        workspace_artifacts=workspace_artifacts,
        skills=registry,
        artifacts=artifacts,
    ), registry, events, sessions, workspace


def test_memory_reconstruction_is_deterministic(tmp_path) -> None:
    service, _, _, sessions, workspace = make_services(tmp_path)
    session_id = sessions.list_sessions()[0].id

    working = service.reconstruct_working_memory(session_id)
    session_memory = service.reconstruct_session_memory(session_id)
    repository_memory = service.reconstruct_repository_memory()

    assert isinstance(working, WorkingMemory)
    assert isinstance(session_memory, SessionMemory)
    assert isinstance(repository_memory, RepositoryMemory)
    assert working.session_id == session_id
    assert session_memory.artifact_ids == ["artifact-1"]
    assert repository_memory.repository_id == workspace.configuration.workspace_id
    assert repository_memory.source_summary.session_count == 1


def test_memory_projection_builders_are_registered() -> None:
    assert "working_memory" in projection_registry.list_projection_types()
    assert "session_memory" in projection_registry.list_projection_types()
    assert "repository_memory" in projection_registry.list_projection_types()


def test_memory_routes_and_diagnostics(tmp_path, monkeypatch) -> None:
    service, registry, _, sessions, _ = make_services(tmp_path)
    session_id = sessions.list_sessions()[0].id
    monkeypatch.setattr(memory_routes, "memory_reconstruction_service", service)
    monkeypatch.setattr(skills_routes, "skill_registry_service", registry)
    monkeypatch.setattr(
        diagnostics_routes,
        "memory_reconstruction_service",
        service,
    )
    monkeypatch.setattr(
        diagnostics_routes,
        "skill_registry_service",
        registry,
    )
    working = memory_routes.get_working_memory(session_id=session_id)
    session = memory_routes.get_session_memory(session_id=session_id)
    repository = memory_routes.get_repository_memory()
    diagnostics = diagnostics_routes.memory_diagnostics()
    skills = skills_routes.list_skills()
    skill_diagnostics = diagnostics_routes.skill_registry_diagnostics()

    assert working.session_id == session_id
    assert session.session_id == session_id
    assert repository.source_summary.session_count == 1
    assert diagnostics["status"] == "healthy"
    assert skills.registered_skills_total == 0
    assert skill_diagnostics["status"] == "healthy"
