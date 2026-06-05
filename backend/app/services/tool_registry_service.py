from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, ToolParameterRecord, ToolRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.runtime_event import EventType, Severity
from app.models.tool import ToolParameterType
from app.services.event_service import EventService, event_service


class ToolNotFoundError(RuntimeError):
    pass


class ToolAlreadyExistsError(RuntimeError):
    pass


class ToolRegistryService:
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

    def register_tool(
        self,
        name: str,
        description: str,
        enabled: bool = True,
        parameters: list[dict[str, object]] | None = None,
    ) -> ToolRecord:
        now = datetime.now(UTC)
        record = ToolRecord(
            id=str(uuid4()),
            name=name,
            description=description,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )

        with self.session_factory() as session:
            session.add(record)
            try:
                session.flush()
            except IntegrityError as exc:
                session.rollback()
                raise ToolAlreadyExistsError(f"Tool already exists: {name}") from exc

            for parameter in parameters or []:
                parameter_type = ToolParameterType(str(parameter["type"]))
                session.add(
                    ToolParameterRecord(
                        id=str(uuid4()),
                        tool_id=record.id,
                        name=str(parameter["name"]),
                        type=parameter_type.value,
                        required=bool(parameter["required"]),
                    )
                )

            session.commit()
            session.refresh(record)
            session.expunge(record)

        self._emit_event(
            EventType.TOOL_REGISTERED,
            record,
            message=f"Tool registered: {record.name}",
        )
        return record

    def get_tool(self, tool_id: str) -> ToolRecord:
        with self.session_factory() as session:
            record = session.get(ToolRecord, tool_id)
            if record is None:
                raise ToolNotFoundError(f"Tool not found: {tool_id}")
            session.expunge(record)

        return record

    def get_tool_by_name(self, name: str) -> ToolRecord:
        with self.session_factory() as session:
            record = session.scalars(
                select(ToolRecord).where(ToolRecord.name == name)
            ).first()
            if record is None:
                raise ToolNotFoundError(f"Tool not found: {name}")
            session.expunge(record)

        return record

    def list_tools(self, enabled_only: bool = False) -> list[ToolRecord]:
        statement = select(ToolRecord)
        if enabled_only:
            statement = statement.where(ToolRecord.enabled.is_(True))
        statement = statement.order_by(ToolRecord.created_at.desc())

        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)

        return list(records)

    def enable_tool(self, tool_id: str) -> ToolRecord:
        record = self._set_enabled(tool_id, enabled=True)
        self._emit_event(
            EventType.TOOL_ENABLED,
            record,
            message=f"Tool enabled: {record.name}",
        )
        return record

    def disable_tool(self, tool_id: str) -> ToolRecord:
        record = self._set_enabled(tool_id, enabled=False)
        self._emit_event(
            EventType.TOOL_DISABLED,
            record,
            message=f"Tool disabled: {record.name}",
        )
        return record

    def list_parameters(self, tool_id: str) -> list[ToolParameterRecord]:
        statement = select(ToolParameterRecord).where(
            ToolParameterRecord.tool_id == tool_id
        )

        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)

        return list(records)

    def _set_enabled(self, tool_id: str, enabled: bool) -> ToolRecord:
        with self.session_factory() as session:
            record = session.get(ToolRecord, tool_id)
            if record is None:
                raise ToolNotFoundError(f"Tool not found: {tool_id}")

            record.enabled = enabled
            record.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        return record

    def _emit_event(
        self,
        event_type: EventType,
        record: ToolRecord,
        message: str,
        severity: Severity = Severity.INFO,
    ) -> None:
        self._events.emit_event_sync(
            event_type=event_type,
            severity=severity,
            message=message,
            metadata={
                "tool_id": record.id,
                "name": record.name,
                "enabled": record.enabled,
                "created_at": record.created_at.isoformat(),
                "updated_at": record.updated_at.isoformat(),
            },
        )


tool_registry_service = ToolRegistryService()
