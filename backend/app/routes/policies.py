from fastapi import APIRouter, HTTPException

from app.db.schema import (
    PolicyDecisionRecord,
    PolicyRecord,
    PolicyVersionRecord,
    PolicyViolationRecord,
)
from app.models.policy import (
    Policy,
    PolicyCreate,
    PolicyDecision,
    PolicyDecisionCreate,
    PolicyDetail,
    PolicyVersion,
    PolicyVersionCreate,
    PolicyViolation,
    PolicyViolationCreate,
)
from app.services.policy_service import (
    PolicyNotFoundError,
    PolicyVersionNotFoundError,
    PolicyVersionPolicyMismatchError,
    policy_service,
)


router = APIRouter()


def to_policy(record: PolicyRecord) -> Policy:
    return Policy(
        id=record.id,
        name=record.name,
        description=record.description,
        policy_type=record.policy_type,
        status=record.status,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


def to_policy_version(record: PolicyVersionRecord) -> PolicyVersion:
    return PolicyVersion(
        id=record.id,
        policy_id=record.policy_id,
        version=record.version,
        rule_payload=policy_service.rule_payload_for(record),
        created_at=record.created_at.isoformat(),
    )


def to_policy_decision(record: PolicyDecisionRecord) -> PolicyDecision:
    return PolicyDecision(
        id=record.id,
        policy_id=record.policy_id,
        policy_version_id=record.policy_version_id,
        target_type=record.target_type,
        target_id=record.target_id,
        decision=record.decision,
        reason=record.reason,
        evaluation_id=record.evaluation_id,
        evaluation_result_id=record.evaluation_result_id,
        metadata=policy_service.decision_metadata_for(record),
        created_at=record.created_at.isoformat(),
    )


def to_policy_violation(record: PolicyViolationRecord) -> PolicyViolation:
    return PolicyViolation(
        id=record.id,
        policy_id=record.policy_id,
        policy_version_id=record.policy_version_id,
        target_type=record.target_type,
        target_id=record.target_id,
        severity=record.severity,
        message=record.message,
        evaluation_id=record.evaluation_id,
        evaluation_result_id=record.evaluation_result_id,
        metadata=policy_service.violation_metadata_for(record),
        created_at=record.created_at.isoformat(),
    )


@router.post("/policies")
def create_policy(request: PolicyCreate) -> Policy:
    return to_policy(
        policy_service.create_policy(
            name=request.name,
            description=request.description,
            policy_type=request.policy_type,
            status=request.status,
        )
    )


@router.get("/policies")
def list_policies() -> list[Policy]:
    return [to_policy(record) for record in policy_service.list_policies()]


@router.get("/policies/{policy_id}")
def get_policy(policy_id: str) -> PolicyDetail:
    try:
        record = policy_service.get_policy(policy_id)
        return PolicyDetail(
            **to_policy(record).model_dump(),
            versions=[
                to_policy_version(version)
                for version in policy_service.list_policy_versions(policy_id)
            ],
            decisions=[
                to_policy_decision(decision)
                for decision in policy_service.list_policy_decisions(policy_id)
            ],
            violations=[
                to_policy_violation(violation)
                for violation in policy_service.list_policy_violations(policy_id)
            ],
        )
    except PolicyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/policies/{policy_id}/versions")
def add_policy_version(
    policy_id: str,
    request: PolicyVersionCreate,
) -> PolicyVersion:
    try:
        return to_policy_version(
            policy_service.add_policy_version(
                policy_id=policy_id,
                version=request.version,
                rule_payload=request.rule_payload,
            )
        )
    except PolicyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/policies/{policy_id}/decisions")
def record_policy_decision(
    policy_id: str,
    request: PolicyDecisionCreate,
) -> PolicyDecision:
    try:
        return to_policy_decision(
            policy_service.record_policy_decision(
                policy_id=policy_id,
                policy_version_id=request.policy_version_id,
                target_type=request.target_type,
                target_id=request.target_id,
                decision=request.decision,
                reason=request.reason,
                metadata=request.metadata,
                evaluation_id=request.evaluation_id,
                evaluation_result_id=request.evaluation_result_id,
            )
        )
    except PolicyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyVersionNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PolicyVersionPolicyMismatchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/policies/{policy_id}/violations")
def record_policy_violation(
    policy_id: str,
    request: PolicyViolationCreate,
) -> PolicyViolation:
    try:
        return to_policy_violation(
            policy_service.record_policy_violation(
                policy_id=policy_id,
                policy_version_id=request.policy_version_id,
                target_type=request.target_type,
                target_id=request.target_id,
                severity=request.severity,
                message=request.message,
                metadata=request.metadata,
                evaluation_id=request.evaluation_id,
                evaluation_result_id=request.evaluation_result_id,
            )
        )
    except PolicyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyVersionNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PolicyVersionPolicyMismatchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
