import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, PlannerRecommendationRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.planner import PlannerRequest, PlannerResponse
from app.models.runtime_event import EventType, Severity
from app.services.event_service import EventService, event_service


class PlannerRecommendationNotFoundError(RuntimeError):
    pass


class PlannerRecommendationService:
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

    def create_recommendation(
        self,
        planner_request: PlannerRequest,
        planner_response: PlannerResponse,
        governance_preview: dict,
    ) -> PlannerRecommendationRecord:
        record = self._create_recommendation_record(
            planner_request=planner_request,
            planner_response=planner_response,
            governance_preview=governance_preview,
        )
        self._emit_event(
            EventType.PLANNER_RECOMMENDATION_CREATED,
            record,
            message=f"Planner recommendation created: {record.id}",
        )
        return record

    async def create_recommendation_async(
        self,
        planner_request: PlannerRequest,
        planner_response: PlannerResponse,
        governance_preview: dict,
    ) -> PlannerRecommendationRecord:
        record = self._create_recommendation_record(
            planner_request=planner_request,
            planner_response=planner_response,
            governance_preview=governance_preview,
        )
        await self._emit_event_async(
            EventType.PLANNER_RECOMMENDATION_CREATED,
            record,
            message=f"Planner recommendation created: {record.id}",
        )
        return record

    def get_recommendation(
        self,
        recommendation_id: str,
    ) -> PlannerRecommendationRecord:
        with self.session_factory() as session:
            record = session.get(PlannerRecommendationRecord, recommendation_id)
            if record is None:
                raise PlannerRecommendationNotFoundError(
                    f"Planner recommendation not found: {recommendation_id}"
                )
            session.expunge(record)

        return record

    def list_recommendations(
        self,
        session_id: str | None = None,
    ) -> list[PlannerRecommendationRecord]:
        statement = select(PlannerRecommendationRecord)
        if session_id is not None:
            statement = statement.where(
                PlannerRecommendationRecord.session_id == session_id
            )
        statement = statement.order_by(PlannerRecommendationRecord.created_at.asc())

        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)

        return list(records)

    def proposed_tool_for(
        self,
        record: PlannerRecommendationRecord,
    ) -> dict | None:
        if record.proposed_tool_json is None:
            return None
        return json.loads(record.proposed_tool_json)

    def _create_recommendation_record(
        self,
        planner_request: PlannerRequest,
        planner_response: PlannerResponse,
        governance_preview: dict,
    ) -> PlannerRecommendationRecord:
        proposed_tool_json = (
            json.dumps(planner_response.proposed_tool.model_dump(mode="json"))
            if planner_response.proposed_tool is not None
            else None
        )
        record = PlannerRecommendationRecord(
            id=str(uuid4()),
            task_id=planner_request.task_id,
            session_id=planner_request.session_id,
            objective=planner_request.objective,
            proposed_tool_json=proposed_tool_json,
            rationale=planner_response.rationale,
            confidence=planner_response.confidence,
            governance_status=str(governance_preview["governance_status"]),
            created_at=datetime.now(UTC),
        )

        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        return record

    def _event_metadata(self, record: PlannerRecommendationRecord) -> dict:
        return {
            "recommendation_id": record.id,
            "task_id": record.task_id,
            "session_id": record.session_id,
            "objective": record.objective,
            "proposed_tool": self.proposed_tool_for(record),
            "rationale": record.rationale,
            "confidence": record.confidence,
            "governance_status": record.governance_status,
            "created_at": record.created_at.isoformat(),
        }

    def _emit_event(
        self,
        event_type: EventType,
        record: PlannerRecommendationRecord,
        message: str,
        severity: Severity = Severity.INFO,
    ) -> None:
        self._events.emit_event_sync(
            event_type=event_type,
            severity=severity,
            message=message,
            metadata=self._event_metadata(record),
        )

    async def _emit_event_async(
        self,
        event_type: EventType,
        record: PlannerRecommendationRecord,
        message: str,
        severity: Severity = Severity.INFO,
    ) -> None:
        await self._events.emit_event(
            event_type=event_type,
            severity=severity,
            message=message,
            metadata=self._event_metadata(record),
        )


planner_recommendation_service = PlannerRecommendationService()
