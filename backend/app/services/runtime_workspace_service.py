from __future__ import annotations

import os
import json
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, RuntimeWorkspaceRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.runtime_workspace import (
    RuntimeWorkspace,
    RuntimeWorkspaceSummary,
)


WORKSPACE_ROOT_ENV = "STRATUM_WORKSPACE_ROOT"
DEFAULT_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


class RuntimeWorkspaceService:
    def __init__(
        self,
        root: str | Path | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None
        source = root
        if source is None:
            values = os.environ if environment is None else environment
            source = values.get(WORKSPACE_ROOT_ENV)
        resolved = Path(source if source is not None else DEFAULT_WORKSPACE_ROOT).expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise ValueError(
                f"Runtime workspace root is not a directory: {resolved}"
            )
        self._root = resolved
        self._db_path = self._root / ".stratum" / "runtime_workspaces.db"
        self._ensure_initialized()
        self._ensure_default_workspace()

    @property
    def root(self) -> Path:
        return Path(self.get_active_workspace().root_path)

    @property
    def configuration(self) -> RuntimeWorkspace:
        return self.get_active_workspace()

    @property
    def session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            self._engine = create_sqlite_engine(self._db_path)
            Base.metadata.create_all(self._engine)
            self._session_factory = create_session_factory(self._engine)
        return self._session_factory

    def _ensure_initialized(self) -> None:
        self.session_factory

    def _ensure_default_workspace(self) -> None:
        with self.session_factory() as session:
            if session.scalar(select(RuntimeWorkspaceRecord.workspace_id).limit(1)) is not None:
                active = session.scalars(
                    select(RuntimeWorkspaceRecord).where(RuntimeWorkspaceRecord.active.is_(True))
                ).first()
                if active is None:
                    first = session.scalars(
                        select(RuntimeWorkspaceRecord).order_by(
                            RuntimeWorkspaceRecord.name,
                            RuntimeWorkspaceRecord.root_path,
                            RuntimeWorkspaceRecord.workspace_id,
                        )
                    ).first()
                    if first is not None:
                        for record in session.scalars(
                            select(RuntimeWorkspaceRecord)
                        ).all():
                            record.active = record.workspace_id == first.workspace_id
                        session.commit()
                return
        self.register_workspace("default", self._root)

    def register_workspace(
        self,
        name: str,
        root_path: str | Path,
    ) -> RuntimeWorkspace:
        resolved = Path(root_path).expanduser().resolve()
        if not resolved.exists():
            raise ValueError(f"Runtime workspace root does not exist: {resolved}")
        if not resolved.is_dir():
            raise ValueError(
                f"Runtime workspace root is not a directory: {resolved}"
            )
        with self.session_factory() as session:
            existing = session.scalar(
                select(RuntimeWorkspaceRecord).where(
                    RuntimeWorkspaceRecord.root_path == resolved.as_posix()
                )
            )
            if existing is not None:
                raise ValueError(
                    f"Runtime workspace root already registered: {resolved}"
                )
            has_active = session.scalar(
                select(RuntimeWorkspaceRecord.workspace_id).where(
                    RuntimeWorkspaceRecord.active.is_(True)
                ).limit(1)
            ) is not None
            record = RuntimeWorkspaceRecord(
                workspace_id=str(uuid.uuid4()),
                name=name,
                root_path=resolved.as_posix(),
                created_at=datetime.now(timezone.utc),
                metadata_json=json.dumps({}, separators=(",", ":")),
                active=not has_active,
            )
            session.add(record)
            if record.active:
                self._deactivate_others(session, record.workspace_id)
            else:
                session.commit()
            return self._to_workspace(record)

    def list_workspaces(self) -> list[RuntimeWorkspaceSummary]:
        with self.session_factory() as session:
            records = session.scalars(
                select(RuntimeWorkspaceRecord).order_by(
                    RuntimeWorkspaceRecord.name,
                    RuntimeWorkspaceRecord.root_path,
                    RuntimeWorkspaceRecord.workspace_id,
                )
            ).all()
        return [
            RuntimeWorkspaceSummary(
                workspace_id=record.workspace_id,
                name=record.name,
                root_path=record.root_path,
                active=record.active,
            )
            for record in records
        ]

    def get_workspace(self, workspace_id: str) -> RuntimeWorkspace:
        with self.session_factory() as session:
            record = session.get(RuntimeWorkspaceRecord, workspace_id)
        if record is None:
            raise ValueError(f"Unknown runtime workspace: {workspace_id}")
        return self._to_workspace(record)

    def get_active_workspace(self) -> RuntimeWorkspace:
        with self.session_factory() as session:
            record = session.scalars(
                select(RuntimeWorkspaceRecord).where(
                    RuntimeWorkspaceRecord.active.is_(True)
                )
            ).first()
            if record is None:
                record = session.scalars(
                    select(RuntimeWorkspaceRecord).order_by(
                        RuntimeWorkspaceRecord.name,
                        RuntimeWorkspaceRecord.root_path,
                        RuntimeWorkspaceRecord.workspace_id,
                    )
                ).first()
                if record is None:
                    raise ValueError("No active runtime workspace registered")
                self._deactivate_others(session, record.workspace_id)
                record = session.get(RuntimeWorkspaceRecord, record.workspace_id)
        assert record is not None
        return self._to_workspace(record)

    def set_active_workspace(self, workspace_id: str) -> RuntimeWorkspace:
        with self.session_factory() as session:
            record = session.get(RuntimeWorkspaceRecord, workspace_id)
            if record is None:
                raise ValueError(f"Unknown runtime workspace: {workspace_id}")
            self._deactivate_others(session, workspace_id)
            record.active = True
            session.add(record)
            session.commit()
            return self._to_workspace(record)

    def validate_relative_path(self, path: str) -> Path:
        candidate_path = Path(path)
        if candidate_path.is_absolute():
            raise ValueError("Workspace path must be relative")
        candidate = (self.root / candidate_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(
                "Workspace path is outside the workspace"
            ) from exc
        return candidate

    def relative_path(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def record_artifact(
        self,
        *,
        tool: str,
        artifact_type: str,
        summary: str,
        session_id: str | None = None,
        path: str | None = None,
        metadata: dict[str, object] | None = None,
        artifact_id: str | None = None,
    ):
        from app.services.runtime_workspace_artifact_service import (
            RuntimeWorkspaceArtifactService,
        )

        return RuntimeWorkspaceArtifactService(self).record_artifact(
            workspace_id=self.configuration.workspace_id,
            tool=tool,
            artifact_type=artifact_type,
            summary=summary,
            session_id=session_id,
            path=path,
            metadata=metadata,
            artifact_id=artifact_id,
        )

    def _deactivate_others(
        self,
        session: Session,
        active_workspace_id: str,
    ) -> None:
        for record in session.scalars(select(RuntimeWorkspaceRecord)).all():
            record.active = record.workspace_id == active_workspace_id
        session.commit()

    def _to_workspace(self, record: RuntimeWorkspaceRecord) -> RuntimeWorkspace:
        return RuntimeWorkspace(
            workspace_id=record.workspace_id,
            name=record.name,
            root_path=record.root_path,
            created_at=record.created_at,
            metadata=json.loads(record.metadata_json or "{}"),
            active=record.active,
        )


runtime_workspace_service = RuntimeWorkspaceService()
