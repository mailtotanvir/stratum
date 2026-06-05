from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, ProposalArtifactLinkRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.runtime_event import EventType, Severity
from app.services.artifact_service import ArtifactService, artifact_service
from app.services.event_service import EventService, event_service
from app.services.proposal_service import ProposalService, proposal_service


class ProposalArtifactAlreadyAttachedError(RuntimeError):
    pass


class ProposalArtifactService:
    def __init__(
        self,
        db_path: Path | None = None,
        artifacts: ArtifactService | None = None,
        proposals: ProposalService | None = None,
        events: EventService | None = None,
    ) -> None:
        self._db_path = db_path
        self._artifacts = artifacts or artifact_service
        self._proposals = proposals or proposal_service
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

    def attach_artifact(
        self,
        proposal_id: str,
        artifact_id: str,
    ) -> ProposalArtifactLinkRecord:
        self._proposals.get_proposal(proposal_id)
        self._artifacts.get_artifact(artifact_id)

        with self.session_factory() as session:
            existing = session.scalars(
                select(ProposalArtifactLinkRecord).where(
                    ProposalArtifactLinkRecord.proposal_id == proposal_id,
                    ProposalArtifactLinkRecord.artifact_id == artifact_id,
                )
            ).first()
            if existing is not None:
                raise ProposalArtifactAlreadyAttachedError(
                    f"Artifact already attached to proposal: {artifact_id}"
                )

            record = ProposalArtifactLinkRecord(
                id=str(uuid4()),
                proposal_id=proposal_id,
                artifact_id=artifact_id,
                created_at=datetime.now(UTC),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        self._emit_event(
            EventType.PROPOSAL_ARTIFACT_ATTACHED,
            record,
            message=f"Proposal artifact attached: {artifact_id}",
        )
        return record

    def list_proposal_artifacts(
        self,
        proposal_id: str,
    ) -> list[ProposalArtifactLinkRecord]:
        return self.list_links(proposal_id=proposal_id)

    def list_links(
        self,
        proposal_id: str | None = None,
    ) -> list[ProposalArtifactLinkRecord]:
        statement = select(ProposalArtifactLinkRecord)
        if proposal_id is not None:
            statement = statement.where(
                ProposalArtifactLinkRecord.proposal_id == proposal_id
            )
        statement = statement.order_by(ProposalArtifactLinkRecord.created_at.desc())

        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)

        return list(records)

    def _emit_event(
        self,
        event_type: EventType,
        record: ProposalArtifactLinkRecord,
        message: str,
        severity: Severity = Severity.INFO,
    ) -> None:
        self._events.emit_event_sync(
            event_type=event_type,
            severity=severity,
            message=message,
            metadata={
                "proposal_artifact_link_id": record.id,
                "proposal_id": record.proposal_id,
                "artifact_id": record.artifact_id,
                "created_at": record.created_at.isoformat(),
            },
        )


proposal_artifact_service = ProposalArtifactService()
