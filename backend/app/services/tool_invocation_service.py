import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, ToolInvocationRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.runtime_event import EventType, Severity
from app.models.tool_invocation import ToolInvocationStatus
from app.services.event_service import EventService, event_service
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)
from app.services.tool_registry_service import (
    ToolRegistryService,
    tool_registry_service,
)


class ToolInvocationNotFoundError(RuntimeError):
    pass


class ToolInvocationService:
    def __init__(
        self,
        db_path: Path | None = None,
        sessions: RuntimeSessionService | None = None,
        tools: ToolRegistryService | None = None,
        events: EventService | None = None,
    ) -> None:
        self._db_path = db_path
        self._sessions = sessions or runtime_session_service
        self._tools = tools or tool_registry_service
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

    def create_invocation(
        self,
        session_id: str,
        tool_id: str,
        input_payload: dict[str, Any] | None = None,
    ) -> ToolInvocationRecord:
        record = self.create_invocation_without_event(
            session_id=session_id,
            tool_id=tool_id,
            input_payload=input_payload,
        )

        self._emit_event(
            EventType.TOOL_INVOCATION_REQUESTED,
            record,
            message=f"Tool invocation requested: {tool_id}",
        )
        return record

    def create_invocation_without_event(
        self,
        session_id: str,
        tool_id: str,
        input_payload: dict[str, Any] | None = None,
    ) -> ToolInvocationRecord:
        self._sessions.get_session(session_id)
        self._tools.get_tool(tool_id)
        record = ToolInvocationRecord(
            id=str(uuid4()),
            session_id=session_id,
            tool_id=tool_id,
            status=ToolInvocationStatus.REQUESTED.value,
            input_payload_json=self._dump_payload(input_payload),
            output_payload_json=None,
            created_at=datetime.now(UTC),
            completed_at=None,
        )

        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        return record

    def mark_running(self, invocation_id: str) -> ToolInvocationRecord:
        record = self._mark(invocation_id, ToolInvocationStatus.RUNNING)
        self._emit_event(
            EventType.TOOL_INVOCATION_RUNNING,
            record,
            message=f"Tool invocation running: {record.tool_id}",
        )
        return record

    def mark_running_without_event(self, invocation_id: str) -> ToolInvocationRecord:
        return self._mark(invocation_id, ToolInvocationStatus.RUNNING)

    def mark_completed(
        self,
        invocation_id: str,
        output_payload: dict[str, Any] | None = None,
    ) -> ToolInvocationRecord:
        record = self._mark(
            invocation_id,
            ToolInvocationStatus.COMPLETED,
            output_payload=output_payload,
            completed_at=datetime.now(UTC),
        )
        self._emit_event(
            EventType.TOOL_INVOCATION_COMPLETED,
            record,
            message=f"Tool invocation completed: {record.tool_id}",
        )
        return record

    def mark_completed_without_event(
        self,
        invocation_id: str,
        output_payload: dict[str, Any] | None = None,
    ) -> ToolInvocationRecord:
        return self._mark(
            invocation_id,
            ToolInvocationStatus.COMPLETED,
            output_payload=output_payload,
            completed_at=datetime.now(UTC),
        )

    def mark_failed(
        self,
        invocation_id: str,
        output_payload: dict[str, Any] | None = None,
    ) -> ToolInvocationRecord:
        record = self._mark(
            invocation_id,
            ToolInvocationStatus.FAILED,
            output_payload=output_payload,
            completed_at=datetime.now(UTC),
        )
        self._emit_event(
            EventType.TOOL_INVOCATION_FAILED,
            record,
            message=f"Tool invocation failed: {record.tool_id}",
            severity=Severity.ERROR,
        )
        return record

    def mark_failed_without_event(
        self,
        invocation_id: str,
        output_payload: dict[str, Any] | None = None,
    ) -> ToolInvocationRecord:
        return self._mark(
            invocation_id,
            ToolInvocationStatus.FAILED,
            output_payload=output_payload,
            completed_at=datetime.now(UTC),
        )

    def get_invocation(self, invocation_id: str) -> ToolInvocationRecord:
        with self.session_factory() as session:
            record = session.get(ToolInvocationRecord, invocation_id)
            if record is None:
                raise ToolInvocationNotFoundError(
                    f"Tool invocation not found: {invocation_id}"
                )
            session.expunge(record)

        return record

    def list_invocations(
        self,
        session_id: str | None = None,
        tool_id: str | None = None,
    ) -> list[ToolInvocationRecord]:
        statement = select(ToolInvocationRecord)
        if session_id is not None:
            statement = statement.where(ToolInvocationRecord.session_id == session_id)
        if tool_id is not None:
            statement = statement.where(ToolInvocationRecord.tool_id == tool_id)
        statement = statement.order_by(ToolInvocationRecord.created_at.desc())

        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)

        return list(records)

    def input_payload_for(self, record: ToolInvocationRecord) -> dict[str, Any] | None:
        return self._load_payload(record.input_payload_json)

    def output_payload_for(self, record: ToolInvocationRecord) -> dict[str, Any] | None:
        return self._load_payload(record.output_payload_json)

    def _mark(
        self,
        invocation_id: str,
        status: ToolInvocationStatus,
        output_payload: dict[str, Any] | None = None,
        completed_at: datetime | None = None,
    ) -> ToolInvocationRecord:
        with self.session_factory() as session:
            record = session.get(ToolInvocationRecord, invocation_id)
            if record is None:
                raise ToolInvocationNotFoundError(
                    f"Tool invocation not found: {invocation_id}"
                )

            record.status = status.value
            if output_payload is not None:
                record.output_payload_json = self._dump_payload(output_payload)
            if completed_at is not None:
                record.completed_at = completed_at
            session.commit()
            session.refresh(record)
            session.expunge(record)

        return record

    def _emit_event(
        self,
        event_type: EventType,
        record: ToolInvocationRecord,
        message: str,
        severity: Severity = Severity.INFO,
    ) -> None:
        metadata: dict[str, Any] = {
            "tool_invocation_id": record.id,
            "session_id": record.session_id,
            "tool_id": record.tool_id,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
        }
        input_payload = self.input_payload_for(record)
        output_payload = self.output_payload_for(record)
        if input_payload is not None:
            metadata["input_payload"] = input_payload
        if output_payload is not None:
            metadata["output_payload"] = output_payload
        if record.completed_at is not None:
            metadata["completed_at"] = record.completed_at.isoformat()

        self._events.emit_event_sync(
            event_type=event_type,
            severity=severity,
            message=message,
            metadata=metadata,
        )

    def _dump_payload(self, payload: dict[str, Any] | None) -> str | None:
        if payload is None:
            return None
        return json.dumps(payload, sort_keys=True)

    def _load_payload(self, payload_json: str | None) -> dict[str, Any] | None:
        if payload_json is None:
            return None
        return dict(json.loads(payload_json))


tool_invocation_service = ToolInvocationService()
