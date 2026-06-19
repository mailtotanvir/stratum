import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import (
    Base,
    PolicyDecisionRecord,
    PolicyRecord,
    PolicyVersionRecord,
    PolicyViolationRecord,
)
from app.db.session import create_session_factory, create_sqlite_engine
from app.models.runtime_event import EventType
from app.services.event_service import EventService, event_service


class PolicyNotFoundError(RuntimeError):
    pass


class PolicyVersionNotFoundError(RuntimeError):
    pass


class PolicyVersionPolicyMismatchError(RuntimeError):
    pass


class PolicyService:
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

    def create_policy(
        self,
        name: str,
        description: str,
        policy_type: str,
        status: str,
    ) -> PolicyRecord:
        now = datetime.now(UTC)
        record = PolicyRecord(
            id=str(uuid4()),
            name=name,
            description=description,
            policy_type=policy_type,
            status=status,
            created_at=now,
            updated_at=now,
        )
        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        self._events.emit_event_sync(
            event_type=EventType.POLICY_CREATED,
            message=f"Policy created: {record.id}",
            metadata={
                "policy_id": record.id,
                "name": record.name,
                "policy_type": record.policy_type,
                "status": record.status,
                "created_at": record.created_at.isoformat(),
                "updated_at": record.updated_at.isoformat(),
            },
        )
        return record

    def add_policy_version(
        self,
        policy_id: str,
        version: int,
        rule_payload: dict[str, Any],
    ) -> PolicyVersionRecord:
        policy = self.get_policy(policy_id)
        record = PolicyVersionRecord(
            id=str(uuid4()),
            policy_id=policy.id,
            version=version,
            rule_payload_json=json.dumps(rule_payload, sort_keys=True),
            created_at=datetime.now(UTC),
        )
        with self.session_factory() as session:
            session.add(record)
            policy_row = session.get(PolicyRecord, policy.id)
            assert policy_row is not None
            policy_row.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            session.expunge(record)

        self._events.emit_event_sync(
            event_type=EventType.POLICY_VERSION_ADDED,
            message=f"Policy version added: {record.id}",
            metadata={
                "policy_id": record.policy_id,
                "policy_version_id": record.id,
                "version": record.version,
                "created_at": record.created_at.isoformat(),
            },
        )
        return record

    def get_policy(self, policy_id: str) -> PolicyRecord:
        with self.session_factory() as session:
            record = session.get(PolicyRecord, policy_id)
            if record is None:
                raise PolicyNotFoundError(f"Policy not found: {policy_id}")
            session.expunge(record)
        return record

    def list_policies(self) -> list[PolicyRecord]:
        statement = select(PolicyRecord).order_by(
            PolicyRecord.created_at.asc(),
            PolicyRecord.id.asc(),
        )
        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)
        return list(records)

    def record_policy_decision(
        self,
        policy_id: str,
        policy_version_id: str,
        target_type: str,
        target_id: str,
        decision: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
        evaluation_id: str | None = None,
        evaluation_result_id: str | None = None,
    ) -> PolicyDecisionRecord:
        version = self.get_policy_version(policy_version_id)
        self._ensure_policy_version_matches(policy_id, version)
        record = PolicyDecisionRecord(
            id=str(uuid4()),
            policy_id=policy_id,
            policy_version_id=policy_version_id,
            target_type=target_type,
            target_id=target_id,
            decision=decision,
            reason=reason,
            evaluation_id=evaluation_id,
            evaluation_result_id=evaluation_result_id,
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

        event_metadata: dict[str, Any] = {
            "policy_id": record.policy_id,
            "policy_version_id": record.policy_version_id,
            "policy_decision_id": record.id,
            "target_type": record.target_type,
            "target_id": record.target_id,
            "decision": record.decision,
            "reason": record.reason,
            "metadata": metadata,
            "created_at": record.created_at.isoformat(),
        }
        if record.evaluation_id is not None:
            event_metadata["evaluation_id"] = record.evaluation_id
        if record.evaluation_result_id is not None:
            event_metadata["evaluation_result_id"] = record.evaluation_result_id
        self._events.emit_event_sync(
            event_type=EventType.POLICY_DECISION_RECORDED,
            message=f"Policy decision recorded: {record.id}",
            metadata=event_metadata,
        )
        return record

    def record_policy_violation(
        self,
        policy_id: str,
        policy_version_id: str,
        target_type: str,
        target_id: str,
        severity: str,
        message: str,
        metadata: dict[str, Any] | None = None,
        evaluation_id: str | None = None,
        evaluation_result_id: str | None = None,
    ) -> PolicyViolationRecord:
        version = self.get_policy_version(policy_version_id)
        self._ensure_policy_version_matches(policy_id, version)
        record = PolicyViolationRecord(
            id=str(uuid4()),
            policy_id=policy_id,
            policy_version_id=policy_version_id,
            target_type=target_type,
            target_id=target_id,
            severity=severity,
            message=message,
            evaluation_id=evaluation_id,
            evaluation_result_id=evaluation_result_id,
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

        event_metadata = {
            "policy_id": record.policy_id,
            "policy_version_id": record.policy_version_id,
            "policy_violation_id": record.id,
            "target_type": record.target_type,
            "target_id": record.target_id,
            "severity": record.severity,
            "message": record.message,
            "metadata": metadata,
            "created_at": record.created_at.isoformat(),
        }
        if record.evaluation_id is not None:
            event_metadata["evaluation_id"] = record.evaluation_id
        if record.evaluation_result_id is not None:
            event_metadata["evaluation_result_id"] = record.evaluation_result_id
        self._events.emit_event_sync(
            event_type=EventType.POLICY_VIOLATION_RECORDED,
            message=f"Policy violation recorded: {record.id}",
            metadata=event_metadata,
        )
        return record

    def get_policy_version(self, policy_version_id: str) -> PolicyVersionRecord:
        with self.session_factory() as session:
            record = session.get(PolicyVersionRecord, policy_version_id)
            if record is None:
                raise PolicyVersionNotFoundError(
                    f"Policy version not found: {policy_version_id}"
                )
            session.expunge(record)
        return record

    def list_policy_versions(self, policy_id: str) -> list[PolicyVersionRecord]:
        self.get_policy(policy_id)
        statement = (
            select(PolicyVersionRecord)
            .where(PolicyVersionRecord.policy_id == policy_id)
            .order_by(
                PolicyVersionRecord.version.asc(),
                PolicyVersionRecord.created_at.asc(),
                PolicyVersionRecord.id.asc(),
            )
        )
        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)
        return list(records)

    def list_policy_decisions(self, policy_id: str) -> list[PolicyDecisionRecord]:
        self.get_policy(policy_id)
        statement = (
            select(PolicyDecisionRecord)
            .where(PolicyDecisionRecord.policy_id == policy_id)
            .order_by(
                PolicyDecisionRecord.created_at.asc(),
                PolicyDecisionRecord.id.asc(),
            )
        )
        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)
        return list(records)

    def list_policy_violations(
        self,
        policy_id: str,
    ) -> list[PolicyViolationRecord]:
        self.get_policy(policy_id)
        statement = (
            select(PolicyViolationRecord)
            .where(PolicyViolationRecord.policy_id == policy_id)
            .order_by(
                PolicyViolationRecord.created_at.asc(),
                PolicyViolationRecord.id.asc(),
            )
        )
        with self.session_factory() as session:
            records = session.scalars(statement).all()
            for record in records:
                session.expunge(record)
        return list(records)

    @staticmethod
    def rule_payload_for(record: PolicyVersionRecord) -> dict[str, Any]:
        return dict(json.loads(record.rule_payload_json))

    @staticmethod
    def decision_metadata_for(
        record: PolicyDecisionRecord,
    ) -> dict[str, Any] | None:
        if record.metadata_json is None:
            return None
        return dict(json.loads(record.metadata_json))

    @staticmethod
    def violation_metadata_for(
        record: PolicyViolationRecord,
    ) -> dict[str, Any] | None:
        if record.metadata_json is None:
            return None
        return dict(json.loads(record.metadata_json))

    @staticmethod
    def _ensure_policy_version_matches(
        policy_id: str,
        version: PolicyVersionRecord,
    ) -> None:
        if version.policy_id != policy_id:
            raise PolicyVersionPolicyMismatchError(
                "Policy version does not belong to policy: "
                f"{version.id}"
            )


policy_service = PolicyService()
