from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, DecisionEvidenceRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.decision_evidence import DecisionEvidenceType
from app.models.runtime_event import EventType
from app.services.decision_record_service import (
    DecisionRecordService,
    decision_record_service,
)
from app.services.event_service import EventService, event_service


class DecisionEvidenceNotFoundError(RuntimeError):
    pass


class DecisionEvidenceService:
    def __init__(
        self,
        db_path: Path | None = None,
        events: EventService | None = None,
        decisions: DecisionRecordService | None = None,
    ) -> None:
        self._db_path = db_path
        self._events = events or event_service
        self._decisions = decisions or decision_record_service
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

    def create_evidence(
        self,
        decision_id: str,
        evidence_type: DecisionEvidenceType | str,
        evidence_reference: str,
        summary: str,
    ) -> DecisionEvidenceRecord:
        self._decisions.get_decision_record(decision_id)
        parsed_evidence_type = DecisionEvidenceType(evidence_type)
        record = DecisionEvidenceRecord(
            evidence_id=str(uuid4()),
            decision_id=decision_id,
            evidence_type=parsed_evidence_type.value,
            evidence_reference=evidence_reference,
            summary=summary,
            created_at=datetime.now(UTC),
        )
        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        self._events.emit_event_sync(
            event_type=EventType.DECISION_EVIDENCE_CREATED,
            message=f"Decision evidence created: {record.evidence_id}",
            metadata={
                "decision_id": record.decision_id,
                "evidence_id": record.evidence_id,
                "evidence_type": record.evidence_type,
                "evidence_reference": record.evidence_reference,
                "summary": record.summary,
                "created_at": record.created_at.isoformat(),
            },
        )
        return record

    def get_evidence(self, evidence_id: str) -> DecisionEvidenceRecord:
        with self.session_factory() as session:
            record = session.get(DecisionEvidenceRecord, evidence_id)
            if record is None:
                raise DecisionEvidenceNotFoundError(
                    f"Decision evidence not found: {evidence_id}"
                )
            session.expunge(record)
        return record

    def list_evidence(
        self,
        decision_id: str | None = None,
    ) -> list[DecisionEvidenceRecord]:
        statement = select(DecisionEvidenceRecord)
        if decision_id is not None:
            statement = statement.where(
                DecisionEvidenceRecord.decision_id == decision_id
            )
        statement = statement.order_by(
            DecisionEvidenceRecord.created_at.asc(),
            DecisionEvidenceRecord.evidence_id.asc(),
        )
        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)
        return list(records)


decision_evidence_service = DecisionEvidenceService()
