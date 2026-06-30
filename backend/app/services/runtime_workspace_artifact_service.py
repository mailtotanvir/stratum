from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.schema import Base, RuntimeWorkspaceArtifactRecord
from app.models.runtime_workspace_artifact import RuntimeWorkspaceArtifact
from app.services.runtime_workspace_service import (
    RuntimeWorkspaceService,
    runtime_workspace_service,
)


class RuntimeWorkspaceArtifactService:
    def __init__(
        self,
        workspace: RuntimeWorkspaceService | None = None,
    ) -> None:
        self._workspace = workspace or runtime_workspace_service

    def record_artifact(
        self,
        *,
        workspace_id: str,
        tool: str,
        artifact_type: str,
        summary: str,
        session_id: str | None = None,
        path: str | None = None,
        metadata: dict[str, object] | None = None,
        artifact_id: str | None = None,
        created_at: datetime | None = None,
    ) -> RuntimeWorkspaceArtifact:
        self._workspace.get_workspace(workspace_id)
        record = RuntimeWorkspaceArtifactRecord(
            artifact_id=artifact_id or str(uuid4()),
            workspace_id=workspace_id,
            session_id=session_id,
            tool=tool,
            path=path,
            artifact_type=artifact_type,
            summary=summary,
            created_at=created_at or datetime.now(UTC),
            metadata_json=json.dumps(metadata or {}, separators=(",", ":")),
        )
        with self._workspace.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)
        return self._to_model(record)

    def list_workspace_artifacts(
        self,
        workspace_id: str,
    ) -> list[RuntimeWorkspaceArtifact]:
        self._workspace.get_workspace(workspace_id)
        statement = (
            select(RuntimeWorkspaceArtifactRecord)
            .where(RuntimeWorkspaceArtifactRecord.workspace_id == workspace_id)
            .order_by(RuntimeWorkspaceArtifactRecord.created_at.desc())
        )
        return self._list(statement)

    def list_session_artifacts(
        self,
        session_id: str,
    ) -> list[RuntimeWorkspaceArtifact]:
        statement = (
            select(RuntimeWorkspaceArtifactRecord)
            .where(RuntimeWorkspaceArtifactRecord.session_id == session_id)
            .order_by(RuntimeWorkspaceArtifactRecord.created_at.desc())
        )
        return self._list(statement)

    def _list(
        self,
        statement,
    ) -> list[RuntimeWorkspaceArtifact]:
        with self._workspace.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)
        return [self._to_model(record) for record in records]

    def _to_model(
        self,
        record: RuntimeWorkspaceArtifactRecord,
    ) -> RuntimeWorkspaceArtifact:
        return RuntimeWorkspaceArtifact(
            artifact_id=record.artifact_id,
            workspace_id=record.workspace_id,
            session_id=record.session_id,
            tool=record.tool,
            path=record.path,
            artifact_type=record.artifact_type,
            summary=record.summary,
            created_at=record.created_at,
            metadata=json.loads(record.metadata_json or "{}"),
        )


runtime_workspace_artifact_service = RuntimeWorkspaceArtifactService()
