from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, StopRequestRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.stop import StopRequestStatus


class StopRequestNotFoundError(RuntimeError):
    pass


class StopRequestAlreadyResolvedError(RuntimeError):
    pass


class StopService:
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
    ) -> StopRequestRecord:
        record = StopRequestRecord(
            id=str(uuid4()),
            task_id=task_id,
            reason=reason,
            status=StopRequestStatus.REQUESTED.value,
            created_at=datetime.now(UTC),
            resolved_at=None,
        )

        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        return record

    def apply_request(self, request_id: str) -> StopRequestRecord:
        return self._resolve_request(
            request_id=request_id,
            status=StopRequestStatus.APPLIED,
        )

    def ignore_request(self, request_id: str) -> StopRequestRecord:
        return self._resolve_request(
            request_id=request_id,
            status=StopRequestStatus.IGNORED,
        )

    def get_request(self, request_id: str) -> StopRequestRecord:
        with self.session_factory() as session:
            record = session.get(StopRequestRecord, request_id)
            if record is None:
                raise StopRequestNotFoundError(
                    f"Stop request not found: {request_id}"
                )
            session.expunge(record)

        return record

    def list_requests(
        self,
        status: str | None = None,
        task_id: str | None = None,
    ) -> list[StopRequestRecord]:
        statement = select(StopRequestRecord)
        if status is not None:
            statement = statement.where(StopRequestRecord.status == status)
        if task_id is not None:
            statement = statement.where(StopRequestRecord.task_id == task_id)
        statement = statement.order_by(StopRequestRecord.created_at.desc())

        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)

        return list(records)

    def _resolve_request(
        self,
        request_id: str,
        status: StopRequestStatus,
    ) -> StopRequestRecord:
        with self.session_factory() as session:
            record = session.get(StopRequestRecord, request_id)
            if record is None:
                raise StopRequestNotFoundError(
                    f"Stop request not found: {request_id}"
                )
            if record.status != StopRequestStatus.REQUESTED.value:
                raise StopRequestAlreadyResolvedError(
                    f"Stop request already resolved: {request_id}"
                )

            record.status = status.value
            record.resolved_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        return record


stop_service = StopService()
