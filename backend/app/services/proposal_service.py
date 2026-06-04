from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, ProposalRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.proposal import ProposalDecision, ProposalStatus
from app.models.runtime_event import EventType, Severity
from app.services.event_service import EventService, event_service


class ProposalNotFoundError(RuntimeError):
    pass


class ProposalAlreadyResolvedError(RuntimeError):
    pass


class InvalidProposalDecisionError(RuntimeError):
    pass


class ProposalService:
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

    def create_proposal(
        self,
        title: str,
        body: str,
        task_id: str | None = None,
    ) -> ProposalRecord:
        record = ProposalRecord(
            id=str(uuid4()),
            task_id=task_id,
            title=title,
            body=body,
            status=ProposalStatus.PROPOSED.value,
            created_at=datetime.now(UTC),
            resolved_at=None,
            decision=None,
        )

        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        self._emit_event(
            EventType.PROPOSAL_GENERATED,
            record,
            message=f"Proposal generated: {record.title}",
        )
        return record

    def list_proposals(
        self,
        status: str | None = None,
        task_id: str | None = None,
    ) -> list[ProposalRecord]:
        statement = select(ProposalRecord)
        if status is not None:
            statement = statement.where(ProposalRecord.status == status)
        if task_id is not None:
            statement = statement.where(ProposalRecord.task_id == task_id)
        statement = statement.order_by(ProposalRecord.created_at.desc())

        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)

        return list(records)

    def get_proposal(self, proposal_id: str) -> ProposalRecord:
        with self.session_factory() as session:
            record = session.get(ProposalRecord, proposal_id)
            if record is None:
                raise ProposalNotFoundError(f"Proposal not found: {proposal_id}")
            session.expunge(record)

        return record

    def respond(self, proposal_id: str, decision: str) -> ProposalRecord:
        try:
            parsed_decision = ProposalDecision(decision)
        except ValueError as exc:
            raise InvalidProposalDecisionError(
                f"Invalid proposal decision: {decision}"
            ) from exc

        with self.session_factory() as session:
            record = session.get(ProposalRecord, proposal_id)
            if record is None:
                raise ProposalNotFoundError(f"Proposal not found: {proposal_id}")
            if record.status != ProposalStatus.PROPOSED.value:
                raise ProposalAlreadyResolvedError(
                    f"Proposal already resolved: {proposal_id}"
                )

            record.decision = parsed_decision.value
            record.status = (
                ProposalStatus.APPROVED.value
                if parsed_decision == ProposalDecision.APPROVE
                else ProposalStatus.REJECTED.value
            )
            record.resolved_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        self._emit_event(
            EventType.PROPOSAL_RESOLVED,
            record,
            message=f"Proposal resolved: {record.title}",
        )
        return record

    def _emit_event(
        self,
        event_type: EventType,
        record: ProposalRecord,
        message: str,
        severity: Severity = Severity.INFO,
    ) -> None:
        metadata = {
            "proposal_id": record.id,
            "title": record.title,
            "body": record.body,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
        }
        if record.task_id is not None:
            metadata["task_id"] = record.task_id
        if record.resolved_at is not None:
            metadata["resolved_at"] = record.resolved_at.isoformat()
        if record.decision is not None:
            metadata["decision"] = record.decision

        self._events.emit_event_sync(
            event_type=event_type,
            severity=severity,
            message=message,
            metadata=metadata,
        )


proposal_service = ProposalService()
