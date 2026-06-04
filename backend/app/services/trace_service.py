import json
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, RuntimeEventRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.runtime_event import RuntimeEvent


class TraceService:
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

    def append_event(self, event: RuntimeEvent) -> None:
        record = RuntimeEventRecord(
            event_id=event.id,
            ts=event.ts,
            type=event.type.value,
            severity=event.severity.value,
            message=event.message,
            metadata_json=json.dumps(event.metadata, separators=(",", ":")),
        )

        with self.session_factory() as session:
            session.add(record)
            session.commit()

    def list_events(
        self,
        event_type: str | None = None,
        task_id: str | None = None,
        proposal_id: str | None = None,
        limit: int | None = None,
    ) -> list[RuntimeEvent]:
        statement = select(RuntimeEventRecord).order_by(RuntimeEventRecord.row_id)

        with self.session_factory() as session:
            records = session.scalars(statement).all()

        events = [
            RuntimeEvent(
                id=record.event_id,
                ts=record.ts,
                type=record.type,
                severity=record.severity,
                message=record.message,
                metadata=json.loads(record.metadata_json),
            )
            for record in records
        ]
        if event_type is not None:
            events = [event for event in events if event.type.value == event_type]
        if task_id is not None:
            events = [
                event
                for event in events
                if event.metadata.get("task_id") == task_id
            ]
        if proposal_id is not None:
            events = [
                event
                for event in events
                if event.metadata.get("proposal_id") == proposal_id
            ]
        if limit is not None:
            events = events[-limit:] if limit > 0 else []

        return events


trace_service = TraceService()
