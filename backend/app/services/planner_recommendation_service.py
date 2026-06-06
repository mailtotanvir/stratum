import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import Base, PlannerRecommendationRecord
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.planner import (
    PlannerRecommendationStatus,
    PlannerRequest,
    PlannerResponse,
)
from app.models.runtime_event import EventType, Severity
from app.services.event_service import EventService, event_service


class PlannerRecommendationNotFoundError(RuntimeError):
    pass


class InvalidPlannerRecommendationTransitionError(RuntimeError):
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
            self._ensure_context_snapshot_column(self._engine)
            self._ensure_status_column(self._engine)
            self._session_factory = create_session_factory(self._engine)
        return self._session_factory

    def create_recommendation(
        self,
        planner_request: PlannerRequest,
        planner_response: PlannerResponse,
        governance_preview: dict,
        context_snapshot: dict | None = None,
    ) -> PlannerRecommendationRecord:
        record = self._create_recommendation_record(
            planner_request=planner_request,
            planner_response=planner_response,
            governance_preview=governance_preview,
            context_snapshot=context_snapshot,
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
        context_snapshot: dict | None = None,
    ) -> PlannerRecommendationRecord:
        record = self._create_recommendation_record(
            planner_request=planner_request,
            planner_response=planner_response,
            governance_preview=governance_preview,
            context_snapshot=context_snapshot,
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
        status: str | None = None,
    ) -> list[PlannerRecommendationRecord]:
        statement = select(PlannerRecommendationRecord)
        if session_id is not None:
            statement = statement.where(
                PlannerRecommendationRecord.session_id == session_id
            )
        if status is not None:
            parsed_status = PlannerRecommendationStatus(status)
            statement = statement.where(
                PlannerRecommendationRecord.status == parsed_status.value
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

    def context_snapshot_for(
        self,
        record: PlannerRecommendationRecord,
    ) -> dict | None:
        if record.context_snapshot_json is None:
            return None
        return json.loads(record.context_snapshot_json)

    def mark_promoted(
        self,
        recommendation_id: str,
    ) -> PlannerRecommendationRecord:
        with self.session_factory() as session:
            record = session.get(PlannerRecommendationRecord, recommendation_id)
            if record is None:
                raise PlannerRecommendationNotFoundError(
                    f"Planner recommendation not found: {recommendation_id}"
                )
            if record.status == PlannerRecommendationStatus.DISMISSED.value:
                raise InvalidPlannerRecommendationTransitionError(
                    "Dismissed planner recommendation cannot be promoted: "
                    f"{recommendation_id}"
                )
            record.status = PlannerRecommendationStatus.PROMOTED.value
            session.commit()
            session.refresh(record)
            session.expunge(record)
        return record

    async def dismiss(
        self,
        recommendation_id: str,
    ) -> PlannerRecommendationRecord:
        with self.session_factory() as session:
            record = session.get(PlannerRecommendationRecord, recommendation_id)
            if record is None:
                raise PlannerRecommendationNotFoundError(
                    f"Planner recommendation not found: {recommendation_id}"
                )
            if record.status == PlannerRecommendationStatus.PROMOTED.value:
                raise InvalidPlannerRecommendationTransitionError(
                    "Promoted planner recommendation cannot be dismissed: "
                    f"{recommendation_id}"
                )
            if record.status == PlannerRecommendationStatus.DISMISSED.value:
                raise InvalidPlannerRecommendationTransitionError(
                    f"Planner recommendation already dismissed: {recommendation_id}"
                )
            record.status = PlannerRecommendationStatus.DISMISSED.value
            session.commit()
            session.refresh(record)
            session.expunge(record)

        await self._emit_event_async(
            EventType.PLANNER_RECOMMENDATION_DISMISSED,
            record,
            message=f"Planner recommendation dismissed: {record.id}",
        )
        return record

    def _create_recommendation_record(
        self,
        planner_request: PlannerRequest,
        planner_response: PlannerResponse,
        governance_preview: dict,
        context_snapshot: dict | None = None,
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
            status=PlannerRecommendationStatus.ACTIVE.value,
            context_snapshot_json=(
                json.dumps(
                    context_snapshot,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                if context_snapshot is not None
                else None
            ),
            created_at=datetime.now(UTC),
        )

        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        return record

    def _event_metadata(self, record: PlannerRecommendationRecord) -> dict:
        metadata = {
            "recommendation_id": record.id,
            "task_id": record.task_id,
            "session_id": record.session_id,
            "objective": record.objective,
            "proposed_tool": self.proposed_tool_for(record),
            "rationale": record.rationale,
            "confidence": record.confidence,
            "governance_status": record.governance_status,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
        }
        context_snapshot = self.context_snapshot_for(record)
        if context_snapshot is not None:
            metadata["context_snapshot"] = context_snapshot
        return metadata

    def _ensure_context_snapshot_column(self, engine: Engine) -> None:
        columns = {
            column["name"]
            for column in inspect(engine).get_columns("planner_recommendations")
        }
        if "context_snapshot_json" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE planner_recommendations "
                        "ADD COLUMN context_snapshot_json TEXT"
                    )
                )

    def _ensure_status_column(self, engine: Engine) -> None:
        columns = {
            column["name"]
            for column in inspect(engine).get_columns("planner_recommendations")
        }
        if "status" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE planner_recommendations "
                        "ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
                    )
                )

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
