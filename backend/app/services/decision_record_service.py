from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, DecisionRecordRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.decision_record import (
    DecisionType,
    SelectedEntityType,
)
from app.models.runtime_event import EventType
from app.services.event_service import EventService, event_service
from app.services.planner_recommendation_service import (
    PlannerRecommendationService,
    planner_recommendation_service,
)
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)


class DecisionRecordNotFoundError(RuntimeError):
    pass


class DecisionRecordEntityMismatchError(RuntimeError):
    pass


class DecisionRecordService:
    def __init__(
        self,
        db_path: Path | None = None,
        events: EventService | None = None,
        recommendations: PlannerRecommendationService | None = None,
        runtime_sessions: RuntimeSessionService | None = None,
    ) -> None:
        self._db_path = db_path
        self._events = events or event_service
        self._recommendations = recommendations or planner_recommendation_service
        self._runtime_sessions = runtime_sessions or runtime_session_service
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

    def create_decision_record(
        self,
        session_id: str,
        decision_type: DecisionType | str,
        selected_entity_id: str,
        rationale: str,
    ) -> DecisionRecordRecord:
        parsed_decision_type = DecisionType(decision_type)
        runtime_session = self._runtime_sessions.get_session(session_id)
        recommendation = self._recommendations.get_recommendation(
            selected_entity_id
        )
        if recommendation.session_id != session_id:
            raise DecisionRecordEntityMismatchError(
                "Planner recommendation does not belong to runtime session: "
                f"{selected_entity_id}"
            )

        record = DecisionRecordRecord(
            decision_id=str(uuid4()),
            session_id=runtime_session.id,
            task_id=runtime_session.task_id,
            decision_type=parsed_decision_type.value,
            selected_entity_id=recommendation.id,
            selected_entity_type=SelectedEntityType.PLANNER_RECOMMENDATION.value,
            rationale=rationale,
            created_at=datetime.now(UTC),
        )
        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        self._events.emit_event_sync(
            event_type=EventType.DECISION_RECORD_CREATED,
            message=f"Decision record created: {record.decision_id}",
            metadata={
                "decision_id": record.decision_id,
                "decision_type": record.decision_type,
                "selected_entity_id": record.selected_entity_id,
                "selected_entity_type": record.selected_entity_type,
                "session_id": record.session_id,
                "task_id": record.task_id,
                "rationale": record.rationale,
                "created_at": record.created_at.isoformat(),
            },
        )
        return record

    def get_decision_record(self, decision_id: str) -> DecisionRecordRecord:
        with self.session_factory() as session:
            record = session.get(DecisionRecordRecord, decision_id)
            if record is None:
                raise DecisionRecordNotFoundError(
                    f"Decision record not found: {decision_id}"
                )
            session.expunge(record)
        return record

    def list_decision_records(
        self,
        session_id: str | None = None,
    ) -> list[DecisionRecordRecord]:
        statement = select(DecisionRecordRecord)
        if session_id is not None:
            statement = statement.where(
                DecisionRecordRecord.session_id == session_id
            )
        statement = statement.order_by(
            DecisionRecordRecord.created_at.asc(),
            DecisionRecordRecord.decision_id.asc(),
        )
        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)
        return list(records)


decision_record_service = DecisionRecordService()
