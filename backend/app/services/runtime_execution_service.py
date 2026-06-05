from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, RuntimeExecutionRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.runtime_execution import RuntimeExecutionState


class RuntimeExecutionNotFoundError(RuntimeError):
    pass


class RuntimeExecutionService:
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

    def start(self, task_id: str) -> RuntimeExecutionRecord:
        now = datetime.now(UTC)
        return self._upsert(
            task_id=task_id,
            state=RuntimeExecutionState.RUNNING,
            started_at=now,
            updated_at=now,
        )

    def interrupt(self, task_id: str) -> RuntimeExecutionRecord:
        now = datetime.now(UTC)
        return self._upsert(
            task_id=task_id,
            state=RuntimeExecutionState.INTERRUPTED,
            interrupted_at=now,
            updated_at=now,
        )

    def stop(self, task_id: str) -> RuntimeExecutionRecord:
        now = datetime.now(UTC)
        return self._upsert(
            task_id=task_id,
            state=RuntimeExecutionState.STOPPED,
            stopped_at=now,
            updated_at=now,
        )

    def get(self, task_id: str) -> RuntimeExecutionRecord:
        with self.session_factory() as session:
            record = session.get(RuntimeExecutionRecord, task_id)
            if record is None:
                raise RuntimeExecutionNotFoundError(
                    f"Runtime execution not found: {task_id}"
                )
            session.expunge(record)

        return record

    def list(self) -> list[RuntimeExecutionRecord]:
        statement = select(RuntimeExecutionRecord).order_by(
            RuntimeExecutionRecord.updated_at.desc()
        )

        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)

        return list(records)

    def _upsert(
        self,
        task_id: str,
        state: RuntimeExecutionState,
        updated_at: datetime,
        started_at: datetime | None = None,
        interrupted_at: datetime | None = None,
        stopped_at: datetime | None = None,
    ) -> RuntimeExecutionRecord:
        with self.session_factory() as session:
            record = session.get(RuntimeExecutionRecord, task_id)
            if record is None:
                record = RuntimeExecutionRecord(
                    task_id=task_id,
                    state=RuntimeExecutionState.IDLE.value,
                    started_at=None,
                    interrupted_at=None,
                    stopped_at=None,
                    updated_at=updated_at,
                )
                session.add(record)

            record.state = state.value
            record.updated_at = updated_at
            if started_at is not None:
                record.started_at = started_at
            if interrupted_at is not None:
                record.interrupted_at = interrupted_at
            if stopped_at is not None:
                record.stopped_at = stopped_at

            session.commit()
            session.refresh(record)
            session.expunge(record)

        return record


runtime_execution_service = RuntimeExecutionService()
