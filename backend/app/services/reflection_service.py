import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, ReflectionRequestRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.reflection import ReflectionRequestStatus
from app.models.runtime_event import EventType, Severity
from app.services.event_service import EventService, event_service


class ReflectionRequestNotFoundError(RuntimeError):
    pass


class ReflectionRequestAlreadyResolvedError(RuntimeError):
    pass


class ReflectionService:
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

    def create_request(
        self,
        task_id: str,
        reasons: list[str],
    ) -> ReflectionRequestRecord:
        record = ReflectionRequestRecord(
            id=str(uuid4()),
            task_id=task_id,
            status=ReflectionRequestStatus.PENDING.value,
            reasons_json=json.dumps(reasons),
            created_at=datetime.now(UTC),
            resolved_at=None,
        )

        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        return record

    def list_requests(
        self,
        status: str | None = None,
        task_id: str | None = None,
    ) -> list[ReflectionRequestRecord]:
        statement = select(ReflectionRequestRecord)
        if status is not None:
            statement = statement.where(ReflectionRequestRecord.status == status)
        if task_id is not None:
            statement = statement.where(ReflectionRequestRecord.task_id == task_id)
        statement = statement.order_by(ReflectionRequestRecord.created_at.desc())

        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)

        return list(records)

    def get_request(self, request_id: str) -> ReflectionRequestRecord:
        with self.session_factory() as session:
            record = session.get(ReflectionRequestRecord, request_id)
            if record is None:
                raise ReflectionRequestNotFoundError(
                    f"Reflection request not found: {request_id}"
                )
            session.expunge(record)

        return record

    def resolve_request(self, request_id: str) -> ReflectionRequestRecord:
        with self.session_factory() as session:
            record = session.get(ReflectionRequestRecord, request_id)
            if record is None:
                raise ReflectionRequestNotFoundError(
                    f"Reflection request not found: {request_id}"
                )
            if record.status == ReflectionRequestStatus.RESOLVED.value:
                raise ReflectionRequestAlreadyResolvedError(
                    f"Reflection request already resolved: {request_id}"
                )

            record.status = ReflectionRequestStatus.RESOLVED.value
            record.resolved_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        self._emit_event(
            EventType.REFLECTION_RESOLVED,
            record,
            message=f"Reflection resolved for task: {record.task_id}",
        )
        return record

    def reasons_for(self, record: ReflectionRequestRecord) -> list[str]:
        return list(json.loads(record.reasons_json))

    def _emit_event(
        self,
        event_type: EventType,
        record: ReflectionRequestRecord,
        message: str,
        severity: Severity = Severity.INFO,
    ) -> None:
        metadata = {
            "reflection_request_id": record.id,
            "task_id": record.task_id,
            "status": record.status,
            "reasons": self.reasons_for(record),
            "created_at": record.created_at.isoformat(),
        }
        if record.resolved_at is not None:
            metadata["resolved_at"] = record.resolved_at.isoformat()

        self._events.emit_event_sync(
            event_type=event_type,
            severity=severity,
            message=message,
            metadata=metadata,
        )


reflection_service = ReflectionService()
