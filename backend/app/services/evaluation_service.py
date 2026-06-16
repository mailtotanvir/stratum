import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import (
    Base,
    EvaluationDimensionRecord,
    EvaluationRecord,
    EvaluationResultRecord,
    EvaluationTargetSnapshotRecord,
)
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.runtime_event import EventType
from app.services.artifact_service import (
    ArtifactNotFoundError,
    ArtifactService,
    artifact_service,
)
from app.services.decision_record_service import (
    DecisionRecordNotFoundError,
    DecisionRecordService,
    decision_record_service,
)
from app.services.event_service import EventService, event_service
from app.services.runtime_session_service import (
    RuntimeSessionNotFoundError,
    RuntimeSessionService,
    runtime_session_service,
)


class EvaluationNotFoundError(RuntimeError):
    pass


class EvaluationDimensionNotFoundError(RuntimeError):
    pass


class EvaluationReferenceRequiredError(RuntimeError):
    pass


class EvaluationTargetSnapshotNotFoundError(RuntimeError):
    pass


class EvaluationService:
    def __init__(
        self,
        db_path: Path | None = None,
        events: EventService | None = None,
        artifacts: ArtifactService | None = None,
        decisions: DecisionRecordService | None = None,
        sessions: RuntimeSessionService | None = None,
    ) -> None:
        self._db_path = db_path
        self._events = events or event_service
        self._artifacts = artifacts or artifact_service
        self._decisions = decisions or decision_record_service
        self._sessions = sessions or runtime_session_service
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

    def create_dimension(
        self,
        name: str,
        description: str,
    ) -> EvaluationDimensionRecord:
        record = EvaluationDimensionRecord(
            id=str(uuid4()),
            name=name,
            description=description,
            created_at=datetime.now(UTC),
        )
        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)
        return record

    def get_dimension(
        self,
        dimension_id: str,
    ) -> EvaluationDimensionRecord:
        with self.session_factory() as session:
            record = session.get(EvaluationDimensionRecord, dimension_id)
            if record is None:
                raise EvaluationDimensionNotFoundError(
                    f"Evaluation dimension not found: {dimension_id}"
                )
            session.expunge(record)
        return record

    def list_dimensions(self) -> list[EvaluationDimensionRecord]:
        statement = select(EvaluationDimensionRecord).order_by(
            EvaluationDimensionRecord.created_at.asc(),
            EvaluationDimensionRecord.id.asc(),
        )
        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)
        return list(records)

    def create_evaluation(
        self,
        evaluation_type: str,
        status: str,
        session_id: str | None = None,
        decision_id: str | None = None,
        artifact_id: str | None = None,
    ) -> EvaluationRecord:
        if not any([session_id, decision_id, artifact_id]):
            raise EvaluationReferenceRequiredError(
                "At least one reference is required: session_id, "
                "decision_id, or artifact_id"
            )

        record = EvaluationRecord(
            id=str(uuid4()),
            session_id=session_id,
            decision_id=decision_id,
            artifact_id=artifact_id,
            evaluation_type=evaluation_type,
            status=status,
            created_at=datetime.now(UTC),
        )
        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        snapshot = self._create_target_snapshot(record)
        self._events.emit_event_sync(
            event_type=EventType.EVALUATION_CREATED,
            message=f"Evaluation created: {record.id}",
            metadata={
                "evaluation_id": record.id,
                "session_id": record.session_id,
                "decision_id": record.decision_id,
                "artifact_id": record.artifact_id,
                "evaluation_type": record.evaluation_type,
                "status": record.status,
                "created_at": record.created_at.isoformat(),
                "target_type": (
                    snapshot.target_type if snapshot is not None else None
                ),
                "target_id": snapshot.target_id if snapshot is not None else None,
            },
        )
        return record

    def add_result(
        self,
        evaluation_id: str,
        dimension_id: str,
        score: float,
        rationale: str,
        metadata: dict[str, Any] | None = None,
    ) -> EvaluationResultRecord:
        evaluation = self.get_evaluation(evaluation_id)
        self.get_dimension(dimension_id)

        record = EvaluationResultRecord(
            id=str(uuid4()),
            evaluation_id=evaluation.id,
            dimension_id=dimension_id,
            score=score,
            rationale=rationale,
            metadata_json=(
                json.dumps(metadata, sort_keys=True)
                if metadata is not None
                else None
            ),
            created_at=datetime.now(UTC),
        )
        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        self._events.emit_event_sync(
            event_type=EventType.EVALUATION_RESULT_ADDED,
            message=f"Evaluation result added: {record.id}",
            metadata={
                "evaluation_result_id": record.id,
                "evaluation_id": record.evaluation_id,
                "dimension_id": record.dimension_id,
                "score": record.score,
                "rationale": record.rationale,
                "metadata": metadata,
                "session_id": evaluation.session_id,
                "decision_id": evaluation.decision_id,
                "artifact_id": evaluation.artifact_id,
                "created_at": record.created_at.isoformat(),
            },
        )
        return record

    def get_evaluation(self, evaluation_id: str) -> EvaluationRecord:
        with self.session_factory() as session:
            record = session.get(EvaluationRecord, evaluation_id)
            if record is None:
                raise EvaluationNotFoundError(
                    f"Evaluation not found: {evaluation_id}"
                )
            session.expunge(record)
        return record

    def get_results(
        self,
        evaluation_id: str,
    ) -> list[EvaluationResultRecord]:
        self.get_evaluation(evaluation_id)
        statement = (
            select(EvaluationResultRecord)
            .where(EvaluationResultRecord.evaluation_id == evaluation_id)
            .order_by(
                EvaluationResultRecord.created_at.asc(),
                EvaluationResultRecord.id.asc(),
            )
        )
        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)
        return list(records)

    def list_evaluations(
        self,
        session_id: str | None = None,
        decision_id: str | None = None,
        artifact_id: str | None = None,
        evaluation_type: str | None = None,
        status: str | None = None,
    ) -> list[EvaluationRecord]:
        statement = select(EvaluationRecord)
        if session_id is not None:
            statement = statement.where(EvaluationRecord.session_id == session_id)
        if decision_id is not None:
            statement = statement.where(EvaluationRecord.decision_id == decision_id)
        if artifact_id is not None:
            statement = statement.where(EvaluationRecord.artifact_id == artifact_id)
        if evaluation_type is not None:
            statement = statement.where(
                EvaluationRecord.evaluation_type == evaluation_type
            )
        if status is not None:
            statement = statement.where(EvaluationRecord.status == status)
        statement = statement.order_by(
            EvaluationRecord.created_at.asc(),
            EvaluationRecord.id.asc(),
        )
        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)
        return list(records)

    def get_target_snapshot(
        self,
        evaluation_id: str,
    ) -> EvaluationTargetSnapshotRecord:
        with self.session_factory() as session:
            record = session.get(EvaluationTargetSnapshotRecord, evaluation_id)
            if record is None:
                raise EvaluationTargetSnapshotNotFoundError(
                    "Evaluation target snapshot not found: "
                    f"{evaluation_id}"
                )
            session.expunge(record)
        return record

    def target_snapshot_for(
        self,
        record: EvaluationTargetSnapshotRecord,
    ) -> dict[str, Any] | None:
        if record.target_metadata_json is None:
            return None
        return dict(json.loads(record.target_metadata_json))

    @staticmethod
    def metadata_for(
        record: EvaluationResultRecord,
    ) -> dict[str, Any] | None:
        if record.metadata_json is None:
            return None
        return dict(json.loads(record.metadata_json))

    def _create_target_snapshot(
        self,
        evaluation: EvaluationRecord,
    ) -> EvaluationTargetSnapshotRecord | None:
        snapshot_payload = self._derive_target_snapshot_payload(evaluation)
        if snapshot_payload is None:
            return None

        record = EvaluationTargetSnapshotRecord(
            evaluation_id=evaluation.id,
            target_type=snapshot_payload["target_type"],
            target_id=snapshot_payload["target_id"],
            target_summary=snapshot_payload["target_summary"],
            target_metadata_json=(
                json.dumps(snapshot_payload["target_metadata"], sort_keys=True)
                if snapshot_payload["target_metadata"] is not None
                else None
            ),
            created_at=evaluation.created_at,
        )
        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)
        return record

    def _derive_target_snapshot_payload(
        self,
        evaluation: EvaluationRecord,
    ) -> dict[str, Any] | None:
        if evaluation.artifact_id is not None:
            try:
                artifact = self._artifacts.get_artifact(evaluation.artifact_id)
            except ArtifactNotFoundError:
                artifact = None
            if artifact is not None:
                return {
                    "target_type": "artifact",
                    "target_id": artifact.id,
                    "target_summary": artifact.path,
                    "target_metadata": {
                        "kind": artifact.kind,
                        "task_id": artifact.task_id,
                        "proposal_id": artifact.proposal_id,
                    },
                }

        if evaluation.decision_id is not None:
            try:
                decision = self._decisions.get_decision_record(
                    evaluation.decision_id
                )
            except DecisionRecordNotFoundError:
                decision = None
            if decision is not None:
                return {
                    "target_type": "decision",
                    "target_id": decision.decision_id,
                    "target_summary": decision.decision_type,
                    "target_metadata": {
                        "session_id": decision.session_id,
                        "task_id": decision.task_id,
                        "selected_entity_id": decision.selected_entity_id,
                        "selected_entity_type": decision.selected_entity_type,
                    },
                }

        if evaluation.session_id is not None:
            try:
                session = self._sessions.get_session(evaluation.session_id)
            except RuntimeSessionNotFoundError:
                session = None
            if session is not None:
                return {
                    "target_type": "session",
                    "target_id": session.id,
                    "target_summary": session.task_id,
                    "target_metadata": {
                        "task_id": session.task_id,
                        "status": session.status,
                    },
                }

        return None


evaluation_service = EvaluationService()
