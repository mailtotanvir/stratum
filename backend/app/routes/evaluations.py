import json

from fastapi import APIRouter, HTTPException

from app.db.schema import (
    EvaluationDimensionRecord,
    EvaluationRecord,
    EvaluationResultRecord,
)
from app.models.evaluation import (
    Evaluation,
    EvaluationCreate,
    EvaluationDetail,
    EvaluationDimension,
    EvaluationDimensionCreate,
    EvaluationResult,
    EvaluationResultCreate,
    EvaluationTargetSnapshot,
)
from app.services.evaluation_service import (
    EvaluationDimensionNotFoundError,
    EvaluationNotFoundError,
    EvaluationReferenceRequiredError,
    EvaluationTargetSnapshotNotFoundError,
    evaluation_service,
)

router = APIRouter()


def to_dimension(record: EvaluationDimensionRecord) -> EvaluationDimension:
    return EvaluationDimension(
        id=record.id,
        name=record.name,
        description=record.description,
        created_at=record.created_at.isoformat(),
    )


def to_evaluation(record: EvaluationRecord) -> Evaluation:
    return Evaluation(
        id=record.id,
        session_id=record.session_id,
        decision_id=record.decision_id,
        artifact_id=record.artifact_id,
        evaluation_type=record.evaluation_type,
        status=record.status,
        created_at=record.created_at.isoformat(),
    )


def to_result(record: EvaluationResultRecord) -> EvaluationResult:
    return EvaluationResult(
        id=record.id,
        evaluation_id=record.evaluation_id,
        dimension_id=record.dimension_id,
        score=record.score,
        rationale=record.rationale,
        metadata=(
            dict(json.loads(record.metadata_json))
            if record.metadata_json is not None
            else None
        ),
        created_at=record.created_at.isoformat(),
    )


def to_target_snapshot(record) -> EvaluationTargetSnapshot:
    return EvaluationTargetSnapshot(
        evaluation_id=record.evaluation_id,
        target_type=record.target_type,
        target_id=record.target_id,
        target_summary=record.target_summary,
        target_metadata=evaluation_service.target_snapshot_for(record),
        created_at=record.created_at.isoformat(),
    )


@router.post("/evaluation-dimensions")
def create_dimension(
    request: EvaluationDimensionCreate,
) -> EvaluationDimension:
    return to_dimension(
        evaluation_service.create_dimension(
            name=request.name,
            description=request.description,
        )
    )


@router.get("/evaluation-dimensions")
def list_dimensions() -> list[EvaluationDimension]:
    return [
        to_dimension(record)
        for record in evaluation_service.list_dimensions()
    ]


@router.post("/evaluations")
def create_evaluation(request: EvaluationCreate) -> Evaluation:
    try:
        return to_evaluation(
            evaluation_service.create_evaluation(
                evaluation_type=request.evaluation_type,
                status=request.status,
                session_id=request.session_id,
                decision_id=request.decision_id,
                artifact_id=request.artifact_id,
            )
        )
    except EvaluationReferenceRequiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/evaluations/{evaluation_id}/results")
def add_result(
    evaluation_id: str,
    request: EvaluationResultCreate,
) -> EvaluationResult:
    try:
        return to_result(
            evaluation_service.add_result(
                evaluation_id=evaluation_id,
                dimension_id=request.dimension_id,
                score=request.score,
                rationale=request.rationale,
                metadata=request.metadata,
            )
        )
    except EvaluationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EvaluationDimensionNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/evaluations/{evaluation_id}")
def get_evaluation(evaluation_id: str) -> EvaluationDetail:
    try:
        record = evaluation_service.get_evaluation(evaluation_id)
        try:
            target_snapshot = to_target_snapshot(
                evaluation_service.get_target_snapshot(evaluation_id)
            )
        except EvaluationTargetSnapshotNotFoundError:
            target_snapshot = None
        return EvaluationDetail(
            **to_evaluation(record).model_dump(),
            target_snapshot=target_snapshot,
            results=[
                to_result(result)
                for result in evaluation_service.get_results(evaluation_id)
            ],
        )
    except EvaluationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/evaluations")
def list_evaluations(
    session_id: str | None = None,
    decision_id: str | None = None,
    artifact_id: str | None = None,
    evaluation_type: str | None = None,
    status: str | None = None,
) -> list[Evaluation]:
    return [
        to_evaluation(record)
        for record in evaluation_service.list_evaluations(
            session_id=session_id,
            decision_id=decision_id,
            artifact_id=artifact_id,
            evaluation_type=evaluation_type,
            status=status,
        )
    ]
