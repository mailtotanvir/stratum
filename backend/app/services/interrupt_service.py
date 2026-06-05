from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, InterruptRequestRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.interrupt import InterruptRequestStatus


class InterruptRequestNotFoundError(RuntimeError):
    pass


class InterruptRequestAlreadyResolvedError(RuntimeError):
    pass


class InterruptService:
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

    def create_request(
        self,
        task_id: str,
        reason: str,
    ) -> InterruptRequestRecord:
        record = InterruptRequestRecord(
            id=str(uuid4()),
            task_id=task_id,
            reason=reason,
            status=InterruptRequestStatus.REQUESTED.value,
            created_at=datetime.now(UTC),
            resolved_at=None,
        )

        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        return record

    def apply_request(self, request_id: str) -> InterruptRequestRecord:
        return self._resolve_request(
            request_id=request_id,
            status=InterruptRequestStatus.APPLIED,
        )

    def ignore_request(self, request_id: str) -> InterruptRequestRecord:
        return self._resolve_request(
            request_id=request_id,
            status=InterruptRequestStatus.IGNORED,
        )

    def get_request(self, request_id: str) -> InterruptRequestRecord:
        with self.session_factory() as session:
            record = session.get(InterruptRequestRecord, request_id)
            if record is None:
                raise InterruptRequestNotFoundError(
                    f"Interrupt request not found: {request_id}"
                )
            session.expunge(record)

        return record

    def list_requests(
        self,
        status: str | None = None,
        task_id: str | None = None,
    ) -> list[InterruptRequestRecord]:
        statement = select(InterruptRequestRecord)
        if status is not None:
            statement = statement.where(InterruptRequestRecord.status == status)
        if task_id is not None:
            statement = statement.where(InterruptRequestRecord.task_id == task_id)
        statement = statement.order_by(InterruptRequestRecord.created_at.desc())

        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)

        return list(records)

    def _resolve_request(
        self,
        request_id: str,
        status: InterruptRequestStatus,
    ) -> InterruptRequestRecord:
        with self.session_factory() as session:
            record = session.get(InterruptRequestRecord, request_id)
            if record is None:
                raise InterruptRequestNotFoundError(
                    f"Interrupt request not found: {request_id}"
                )
            if record.status != InterruptRequestStatus.REQUESTED.value:
                raise InterruptRequestAlreadyResolvedError(
                    f"Interrupt request already resolved: {request_id}"
                )

            record.status = status.value
            record.resolved_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        return record


interrupt_service = InterruptService()
