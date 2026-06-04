from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, TaskRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.runtime_event import EventType, Severity
from app.models.task import TaskStatus
from app.services.event_service import EventService, event_service


class TaskNotFoundError(RuntimeError):
    pass


class TaskService:
    def __init__(
        self,
        db_path: Path | None = None,
        events: EventService | None = None,
    ) -> None:
        self._db_path = db_path
        self._events = events or event_service
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            self._engine = create_sqlite_engine(self._db_path)
            Base.metadata.create_all(self._engine)
            self._session_factory = create_session_factory(self._engine)
        return self._session_factory

    def create_task(self, title: str) -> TaskRecord:
        now = datetime.now(UTC)
        record = TaskRecord(
            id=str(uuid4()),
            title=title,
            status=TaskStatus.CREATED.value,
            created_at=now,
            completed_at=None,
            summary=None,
        )

        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)

        self._emit_lifecycle_event(
            EventType.TASK_CREATED,
            record,
            message=f"Task created: {record.title}",
        )
        return record

    def get_task(self, task_id: str) -> TaskRecord:
        with self.session_factory() as session:
            record = session.get(TaskRecord, task_id)
            if record is None:
                raise TaskNotFoundError(f"Task not found: {task_id}")
            session.expunge(record)

        return record

    def list_tasks(self) -> list[TaskRecord]:
        statement = select(TaskRecord).order_by(TaskRecord.created_at.desc())

        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)

        return list(records)

    def mark_running(self, task_id: str) -> TaskRecord:
        return self._update_lifecycle(
            task_id=task_id,
            status=TaskStatus.RUNNING,
            event_type=EventType.TASK_RUNNING,
            message="Task running",
        )

    def mark_completed(
        self, task_id: str, summary: str | None = None
    ) -> TaskRecord:
        return self._update_lifecycle(
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            event_type=EventType.TASK_COMPLETED,
            message="Task completed",
            summary=summary,
            completed_at=datetime.now(UTC),
        )

    def mark_failed(self, task_id: str, summary: str | None = None) -> TaskRecord:
        return self._update_lifecycle(
            task_id=task_id,
            status=TaskStatus.FAILED,
            event_type=EventType.TASK_FAILED,
            message="Task failed",
            summary=summary,
            completed_at=datetime.now(UTC),
            severity=Severity.ERROR,
        )

    def _update_lifecycle(
        self,
        task_id: str,
        status: TaskStatus,
        event_type: EventType,
        message: str,
        summary: str | None = None,
        completed_at: datetime | None = None,
        severity: Severity = Severity.INFO,
    ) -> TaskRecord:
        with self.session_factory() as session:
            record = session.get(TaskRecord, task_id)
            if record is None:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            record.status = status.value
            if summary is not None:
                record.summary = summary
            if completed_at is not None:
                record.completed_at = completed_at
            session.commit()
            session.refresh(record)
            session.expunge(record)

        self._emit_lifecycle_event(
            event_type,
            record,
            message=f"{message}: {record.title}",
            severity=severity,
        )
        return record

    def _emit_lifecycle_event(
        self,
        event_type: EventType,
        record: TaskRecord,
        message: str,
        severity: Severity = Severity.INFO,
    ) -> None:
        metadata = {
            "task_id": record.id,
            "title": record.title,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
        }
        if record.completed_at is not None:
            metadata["completed_at"] = record.completed_at.isoformat()
        if record.summary is not None:
            metadata["summary"] = record.summary

        self._events.emit_event_sync(
            event_type=event_type,
            severity=severity,
            message=message,
            metadata=metadata,
        )


task_service = TaskService()
