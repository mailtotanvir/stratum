from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, RuntimeSessionRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.runtime_session import RuntimeSessionStatus


class RuntimeSessionNotFoundError(RuntimeError):
    pass


class RuntimeSessionService:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path
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

    def create_session(self, task_id: str) -> RuntimeSessionRecord:
        record = RuntimeSessionRecord(
            id=str(uuid4()),
            task_id=task_id,
            status=RuntimeSessionStatus.CREATED.value,
            created_at=datetime.now(UTC),
            completed_at=None,
        )

        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        return record

    def mark_running(self, session_id: str) -> RuntimeSessionRecord:
        return self._mark(
            session_id=session_id,
            status=RuntimeSessionStatus.RUNNING,
        )

    def mark_completed(self, session_id: str) -> RuntimeSessionRecord:
        return self._mark(
            session_id=session_id,
            status=RuntimeSessionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )

    def mark_interrupted(self, session_id: str) -> RuntimeSessionRecord:
        return self._mark(
            session_id=session_id,
            status=RuntimeSessionStatus.INTERRUPTED,
            completed_at=datetime.now(UTC),
        )

    def mark_stopped(self, session_id: str) -> RuntimeSessionRecord:
        return self._mark(
            session_id=session_id,
            status=RuntimeSessionStatus.STOPPED,
            completed_at=datetime.now(UTC),
        )

    def get_session(self, session_id: str) -> RuntimeSessionRecord:
        with self.session_factory() as session:
            record = session.get(RuntimeSessionRecord, session_id)
            if record is None:
                raise RuntimeSessionNotFoundError(
                    f"Runtime session not found: {session_id}"
                )
            session.expunge(record)

        return record

    def list_sessions(
        self,
        task_id: str | None = None,
    ) -> list[RuntimeSessionRecord]:
        statement = select(RuntimeSessionRecord)
        if task_id is not None:
            statement = statement.where(RuntimeSessionRecord.task_id == task_id)
        statement = statement.order_by(RuntimeSessionRecord.created_at.desc())

        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)

        return list(records)

    def latest_session_for_task(
        self,
        task_id: str,
    ) -> RuntimeSessionRecord | None:
        with self.session_factory() as session:
            record = session.scalars(
                select(RuntimeSessionRecord)
                .where(RuntimeSessionRecord.task_id == task_id)
                .order_by(RuntimeSessionRecord.created_at.desc())
            ).first()
            if record is not None:
                session.expunge(record)

        return record

    def _mark(
        self,
        session_id: str,
        status: RuntimeSessionStatus,
        completed_at: datetime | None = None,
    ) -> RuntimeSessionRecord:
        with self.session_factory() as session:
            record = session.get(RuntimeSessionRecord, session_id)
            if record is None:
                raise RuntimeSessionNotFoundError(
                    f"Runtime session not found: {session_id}"
                )

            record.status = status.value
            if completed_at is not None:
                record.completed_at = completed_at
            session.commit()
            session.refresh(record)
            session.expunge(record)

        return record


runtime_session_service = RuntimeSessionService()
