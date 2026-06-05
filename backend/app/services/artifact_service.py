import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import ArtifactRecord, Base
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.artifact import ArtifactKind
from app.models.runtime_event import EventType, Severity
from app.services.event_service import EventService, event_service


class ArtifactNotFoundError(RuntimeError):
    pass


class InvalidArtifactKindError(RuntimeError):
    pass


class ArtifactService:
    def __init__(
        self,
        db_path: Path | None = None,
        events: EventService | None = None,
    ) -> None:
        self._db_path = db_path
        self._events = events or event_service
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

    def create_artifact(
        self,
        path: str,
        kind: str = ArtifactKind.UNKNOWN.value,
        task_id: str | None = None,
        proposal_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        record = self.create_artifact_without_event(
            path=path,
            kind=kind,
            task_id=task_id,
            proposal_id=proposal_id,
            metadata=metadata,
        )

        self._emit_event(
            EventType.ARTIFACT_CREATED,
            record,
            message=f"Artifact registered: {record.path}",
        )
        return record

    def create_artifact_without_event(
        self,
        path: str,
        kind: str = ArtifactKind.UNKNOWN.value,
        task_id: str | None = None,
        proposal_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        try:
            parsed_kind = ArtifactKind(kind)
        except ValueError as exc:
            raise InvalidArtifactKindError(f"Invalid artifact kind: {kind}") from exc

        record = ArtifactRecord(
            id=str(uuid4()),
            task_id=task_id,
            proposal_id=proposal_id,
            path=path,
            kind=parsed_kind.value,
            created_at=datetime.now(UTC),
            metadata_json=(
                json.dumps(metadata, sort_keys=True)
                if metadata is not None
                else None
            ),
        )

        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        return record

    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        with self.session_factory() as session:
            record = session.get(ArtifactRecord, artifact_id)
            if record is None:
                raise ArtifactNotFoundError(f"Artifact not found: {artifact_id}")
            session.expunge(record)

        return record

    def list_artifacts(
        self,
        task_id: str | None = None,
        proposal_id: str | None = None,
        kind: str | None = None,
    ) -> list[ArtifactRecord]:
        statement = select(ArtifactRecord)
        if task_id is not None:
            statement = statement.where(ArtifactRecord.task_id == task_id)
        if proposal_id is not None:
            statement = statement.where(ArtifactRecord.proposal_id == proposal_id)
        if kind is not None:
            statement = statement.where(ArtifactRecord.kind == kind)
        statement = statement.order_by(ArtifactRecord.created_at.desc())

        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)

        return list(records)

    def metadata_for(self, record: ArtifactRecord) -> dict[str, Any] | None:
        if record.metadata_json is None:
            return None
        return dict(json.loads(record.metadata_json))

    def _emit_event(
        self,
        event_type: EventType,
        record: ArtifactRecord,
        message: str,
        severity: Severity = Severity.INFO,
    ) -> None:
        metadata: dict[str, Any] = {
            "artifact_id": record.id,
            "path": record.path,
            "kind": record.kind,
            "created_at": record.created_at.isoformat(),
        }
        if record.task_id is not None:
            metadata["task_id"] = record.task_id
        if record.proposal_id is not None:
            metadata["proposal_id"] = record.proposal_id
        artifact_metadata = self.metadata_for(record)
        if artifact_metadata is not None:
            metadata["metadata"] = artifact_metadata

        self._events.emit_event_sync(
            event_type=event_type,
            severity=severity,
            message=message,
            metadata=metadata,
        )


artifact_service = ArtifactService()
