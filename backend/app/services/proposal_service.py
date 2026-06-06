import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, ProposalRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.proposal import ProposalDecision, ProposalSourceType, ProposalStatus
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
            self._ensure_source_context_snapshot_column(self._engine)
            self._session_factory = create_session_factory(self._engine)
        return self._session_factory

    def set_db_path(self, db_path: Path | None) -> None:
        self._db_path = db_path
        self._engine = None
        self._session_factory = None

    def create_proposal(
        self,
        title: str,
        body: str,
        task_id: str | None = None,
        source_type: str = ProposalSourceType.MANUAL.value,
        source_id: str | None = None,
        source_context_snapshot: dict | None = None,
    ) -> ProposalRecord:
        record = self._create_proposal_record(
            title=title,
            body=body,
            task_id=task_id,
            source_type=source_type,
            source_id=source_id,
            source_context_snapshot=source_context_snapshot,
        )

        self._emit_event(
            EventType.PROPOSAL_GENERATED,
            record,
            message=f"Proposal generated: {record.title}",
        )
        return record

    async def create_proposal_async(
        self,
        title: str,
        body: str,
        task_id: str | None = None,
        source_type: str = ProposalSourceType.MANUAL.value,
        source_id: str | None = None,
        source_context_snapshot: dict | None = None,
    ) -> ProposalRecord:
        record = self._create_proposal_record(
            title=title,
            body=body,
            task_id=task_id,
            source_type=source_type,
            source_id=source_id,
            source_context_snapshot=source_context_snapshot,
        )

        await self._emit_event_async(
            EventType.PROPOSAL_GENERATED,
            record,
            message=f"Proposal generated: {record.title}",
        )
        return record

    def _create_proposal_record(
        self,
        title: str,
        body: str,
        task_id: str | None = None,
        source_type: str = ProposalSourceType.MANUAL.value,
        source_id: str | None = None,
        source_context_snapshot: dict | None = None,
    ) -> ProposalRecord:
        parsed_source_type = ProposalSourceType(source_type)
        record = ProposalRecord(
            id=str(uuid4()),
            task_id=task_id,
            source_type=parsed_source_type.value,
            source_id=source_id,
            source_context_snapshot_json=(
                json.dumps(
                    source_context_snapshot,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                if source_context_snapshot is not None
                else None
            ),
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

    def source_context_snapshot_for(
        self,
        record: ProposalRecord,
    ) -> dict | None:
        if record.source_context_snapshot_json is None:
            return None
        return json.loads(record.source_context_snapshot_json)

    def get_proposal_source(self, proposal_id: str) -> dict[str, object]:
        record = self.get_proposal(proposal_id)
        source = {
            "proposal_id": record.id,
            "source_type": record.source_type,
            "source_id": record.source_id,
            "source_context_snapshot": self.source_context_snapshot_for(record),
        }
        if record.source_type == ProposalSourceType.PLANNER_RECOMMENDATION.value:
            source["recommendation_id"] = record.source_id
        return source

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
        metadata = self._event_metadata(event_type, record)

        self._events.emit_event_sync(
            event_type=event_type,
            severity=severity,
            message=message,
            metadata=metadata,
        )

    async def _emit_event_async(
        self,
        event_type: EventType,
        record: ProposalRecord,
        message: str,
        severity: Severity = Severity.INFO,
    ) -> None:
        metadata = self._event_metadata(event_type, record)

        await self._events.emit_event(
            event_type=event_type,
            severity=severity,
            message=message,
            metadata=metadata,
        )

    def _event_metadata(
        self,
        event_type: EventType,
        record: ProposalRecord,
    ) -> dict[str, object]:
        source_context_snapshot = self.source_context_snapshot_for(record)
        metadata = {
            "proposal_id": record.id,
            "source_type": record.source_type,
            "source_id": record.source_id,
            "title": record.title,
            "body": record.body,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
            "has_source_context_snapshot": source_context_snapshot is not None,
        }
        if (
            event_type == EventType.PROPOSAL_GENERATED
            and source_context_snapshot is not None
        ):
            metadata["source_context_snapshot"] = source_context_snapshot
        if record.task_id is not None:
            metadata["task_id"] = record.task_id
        if record.resolved_at is not None:
            metadata["resolved_at"] = record.resolved_at.isoformat()
        if record.decision is not None:
            metadata["decision"] = record.decision

        return metadata

    def _ensure_source_context_snapshot_column(self, engine: Engine) -> None:
        columns = {
            column["name"]
            for column in inspect(engine).get_columns("proposals")
        }
        if "source_context_snapshot_json" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE proposals "
                        "ADD COLUMN source_context_snapshot_json TEXT"
                    )
                )


proposal_service = ProposalService()
