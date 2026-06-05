from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, RuntimeArtifactLinkRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.runtime_event import EventType, Severity
from app.services.artifact_service import ArtifactService, artifact_service
from app.services.event_service import EventService, event_service
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)


class RuntimeArtifactAlreadyAttachedError(RuntimeError):
    pass


class RuntimeArtifactSessionMismatchError(RuntimeError):
    pass


class RuntimeArtifactService:
    def __init__(
        self,
        db_path: Path | None = None,
        artifacts: ArtifactService | None = None,
        events: EventService | None = None,
        sessions: RuntimeSessionService | None = None,
    ) -> None:
        self._db_path = db_path
        self._artifacts = artifacts or artifact_service
        self._events = events or event_service
        self._sessions = sessions or runtime_session_service
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    def set_db_path(self, db_path: Path | None) -> None:
        self._db_path = db_path
        self._engine = None
        self._session_factory = None

    @property
    def session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            self._engine = create_sqlite_engine(self._db_path)
            Base.metadata.create_all(self._engine)
            self._session_factory = create_session_factory(self._engine)
        return self._session_factory

    def attach_artifact(
        self,
        task_id: str,
        artifact_id: str,
        session_id: str | None = None,
    ) -> RuntimeArtifactLinkRecord:
        record = self.attach_artifact_without_event(
            task_id=task_id,
            artifact_id=artifact_id,
            session_id=session_id,
        )

        self._emit_event(
            EventType.RUNTIME_ARTIFACT_ATTACHED,
            record,
            message=f"Runtime artifact attached: {artifact_id}",
        )
        return record

    def attach_artifact_without_event(
        self,
        task_id: str,
        artifact_id: str,
        session_id: str | None = None,
    ) -> RuntimeArtifactLinkRecord:
        self._artifacts.get_artifact(artifact_id)
        if session_id is not None:
            runtime_session = self._sessions.get_session(session_id)
            if runtime_session.task_id != task_id:
                raise RuntimeArtifactSessionMismatchError(
                    f"Runtime session does not belong to task: {session_id}"
                )

        with self.session_factory() as session:
            statement = select(RuntimeArtifactLinkRecord).where(
                RuntimeArtifactLinkRecord.task_id == task_id,
                RuntimeArtifactLinkRecord.artifact_id == artifact_id,
            )
            if session_id is None:
                statement = statement.where(
                    RuntimeArtifactLinkRecord.session_id.is_(None)
                )
            else:
                statement = statement.where(
                    RuntimeArtifactLinkRecord.session_id == session_id
                )
            existing = session.scalars(statement).first()
            if existing is not None:
                raise RuntimeArtifactAlreadyAttachedError(
                    f"Artifact already attached to runtime task: {artifact_id}"
                )

            record = RuntimeArtifactLinkRecord(
                id=str(uuid4()),
                task_id=task_id,
                artifact_id=artifact_id,
                session_id=session_id,
                created_at=datetime.now(UTC),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        return record

    def list_task_artifacts(
        self,
        task_id: str,
        session_id: str | None = None,
    ) -> list[RuntimeArtifactLinkRecord]:
        return self.list_links(task_id=task_id, session_id=session_id)

    def list_links(
        self,
        task_id: str | None = None,
        session_id: str | None = None,
    ) -> list[RuntimeArtifactLinkRecord]:
        statement = select(RuntimeArtifactLinkRecord)
        if task_id is not None:
            statement = statement.where(RuntimeArtifactLinkRecord.task_id == task_id)
        if session_id is not None:
            statement = statement.where(
                RuntimeArtifactLinkRecord.session_id == session_id
            )
        statement = statement.order_by(RuntimeArtifactLinkRecord.created_at.desc())

        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)

        return list(records)

    def _emit_event(
        self,
        event_type: EventType,
        record: RuntimeArtifactLinkRecord,
        message: str,
        severity: Severity = Severity.INFO,
    ) -> None:
        metadata = {
            "runtime_artifact_link_id": record.id,
            "task_id": record.task_id,
            "artifact_id": record.artifact_id,
            "created_at": record.created_at.isoformat(),
        }
        if record.session_id is not None:
            metadata["session_id"] = record.session_id

        self._events.emit_event_sync(
            event_type=event_type,
            severity=severity,
            message=message,
            metadata=metadata,
        )


runtime_artifact_service = RuntimeArtifactService()
