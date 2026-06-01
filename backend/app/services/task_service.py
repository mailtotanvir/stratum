from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, TaskRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.task import Task, TaskStatus


class TaskNotFoundError(RuntimeError):
    pass


class TaskService:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            self._engine = create_sqlite_engine(self._db_path)
            Base.metadata.create_all(self._engine)
            self._session_factory = create_session_factory(self._engine)
        return self._session_factory

    def create_task(self, description: str) -> Task:
        now = datetime.now(UTC).isoformat()
        record = TaskRecord(
            id=str(uuid4()),
            created_at=now,
            updated_at=now,
            status=TaskStatus.PENDING.value,
            description=description,
        )

        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_model(record)

    def get_task(self, task_id: str) -> Task:
        with self.session_factory() as session:
            record = session.get(TaskRecord, task_id)

        if record is None:
            raise TaskNotFoundError(f"Task not found: {task_id}")

        return self._to_model(record)

    def list_tasks(self) -> list[Task]:
        statement = select(TaskRecord).order_by(TaskRecord.created_at.desc())

        with self.session_factory() as session:
            records = session.scalars(statement).all()

        return [self._to_model(record) for record in records]

    def update_status(self, task_id: str, status: TaskStatus) -> Task:
        with self.session_factory() as session:
            record = session.get(TaskRecord, task_id)
            if record is None:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            record.status = status.value
            record.updated_at = datetime.now(UTC).isoformat()
            session.commit()
            session.refresh(record)
            return self._to_model(record)

    def _to_model(self, record: TaskRecord) -> Task:
        return Task(
            id=record.id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            status=record.status,
            description=record.description,
        )


task_service = TaskService()

