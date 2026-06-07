import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.schema import (
    ArtifactRecord,
    RuntimeArtifactLinkRecord,
    RuntimeExecutionRecord,
    ToolParameterRecord,
    ToolRecord,
)
from app.models.artifact import Artifact
from app.models.cognitive_state import CognitiveState
from app.models.decision_evidence import (
    DecisionEvidence,
    DecisionEvidenceCreate,
)
from app.models.decision_record import DecisionRecord, DecisionRecordCreate
from app.models.planner import (
    PlannerPreviewRequest,
    PlannerProposalPreviewResponse,
    PlannerProposalResponse,
    PlannerRequest,
    PlannerRecommendation,
    PlannerRecommendationPromotionResponse,
    PlannerRecommendationResponse,
    PlannerRecommendationStatus,
    PlannerResponse,
    RecommendationSelectionPreview,
)
from app.models.planning_context import PlanningContext
from app.models.proposal import Proposal
from app.models.proposal import ProposalSourceType
from app.models.runtime_artifact import RuntimeArtifactAttachment, RuntimeTaskArtifact
from app.models.runtime_execution import RuntimeExecution
from app.models.runtime_event import EventType
from app.models.runtime_session import RuntimeSession
from app.models.tool import Tool, ToolParameter
from app.runtime.python_async_runtime import python_async_runtime
from app.runtime.work_loop import work_loop_service
from app.services.artifact_service import ArtifactNotFoundError, artifact_service
from app.services.cognitive_state_service import cognitive_state_service
from app.services.decision_evidence_service import decision_evidence_service
from app.services.decision_record_service import (
    DecisionRecordEntityMismatchError,
    DecisionRecordNotFoundError,
    decision_record_service,
)
from app.services.event_service import event_service
from app.services.governance_service import governance_service
from app.services.planner_recommendation_service import (
    InvalidPlannerRecommendationTransitionError,
    PlannerRecommendationNotFoundError,
    planner_recommendation_service,
)
from app.services.planner_input_builder_service import (
    planner_input_builder_service,
)
from app.services.planner_service import planner_service
from app.services.planning_context_service import planning_context_service
from app.services.proposal_service import proposal_service
from app.services.recommendation_selection_service import (
    recommendation_selection_service,
)
from app.services.runtime_artifact_service import (
    RuntimeArtifactAlreadyAttachedError,
    RuntimeArtifactSessionMismatchError,
    runtime_artifact_service,
)
from app.services.runtime_execution_service import (
    RuntimeExecutionNotFoundError,
    runtime_execution_service,
)
from app.services.runtime_session_service import (
    RuntimeSessionNotFoundError,
    runtime_session_service,
)
from app.services.tool_execution_service import ToolDisabledError
from app.services.tool_registry_service import ToolNotFoundError, tool_registry_service

router = APIRouter()


class RuntimeReasonRequest(BaseModel):
    reason: str


class RuntimeWorkRequest(BaseModel):
    tool_name: str
    input_payload: dict | None = None


def to_runtime_execution(record: RuntimeExecutionRecord) -> RuntimeExecution:
    return RuntimeExecution(
        task_id=record.task_id,
        state=record.state,
        started_at=(
            record.started_at.isoformat()
            if record.started_at is not None
            else None
        ),
        interrupted_at=(
            record.interrupted_at.isoformat()
            if record.interrupted_at is not None
            else None
        ),
        stopped_at=(
            record.stopped_at.isoformat()
            if record.stopped_at is not None
            else None
        ),
        updated_at=record.updated_at.isoformat(),
    )


def to_runtime_session(record) -> RuntimeSession:
    return RuntimeSession(
        id=record.id,
        task_id=record.task_id,
        status=record.status,
        created_at=record.created_at.isoformat(),
        completed_at=(
            record.completed_at.isoformat()
            if record.completed_at is not None
            else None
        ),
    )


def to_proposal(record) -> Proposal:
    return Proposal(
        id=record.id,
        task_id=record.task_id,
        source_type=record.source_type,
        source_id=record.source_id,
        source_context_snapshot=proposal_service.source_context_snapshot_for(record),
        title=record.title,
        body=record.body,
        status=record.status,
        created_at=record.created_at.isoformat(),
        resolved_at=(
            record.resolved_at.isoformat()
            if record.resolved_at is not None
            else None
        ),
        decision=record.decision,
    )


def to_tool_parameter(record: ToolParameterRecord) -> ToolParameter:
    return ToolParameter(
        id=record.id,
        tool_id=record.tool_id,
        name=record.name,
        type=record.type,
        required=record.required,
    )


def to_available_tool(record: ToolRecord) -> Tool:
    return Tool(
        id=record.id,
        name=record.name,
        description=record.description,
        enabled=record.enabled,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
        parameters=[
            to_tool_parameter(parameter)
            for parameter in tool_registry_service.list_parameters(record.id)
        ],
    )


def to_planner_recommendation(record) -> PlannerRecommendation:
    return PlannerRecommendation(
        id=record.id,
        task_id=record.task_id,
        session_id=record.session_id,
        objective=record.objective,
        proposed_tool=planner_recommendation_service.proposed_tool_for(record),
        rationale=record.rationale,
        confidence=record.confidence,
        governance_status=record.governance_status,
        status=record.status,
        context_snapshot=planner_recommendation_service.context_snapshot_for(record),
        created_at=record.created_at.isoformat(),
    )


def to_decision_record(record) -> DecisionRecord:
    return DecisionRecord(
        decision_id=record.decision_id,
        session_id=record.session_id,
        task_id=record.task_id,
        decision_type=record.decision_type,
        selected_entity_id=record.selected_entity_id,
        selected_entity_type=record.selected_entity_type,
        rationale=record.rationale,
        created_at=record.created_at.isoformat(),
    )


def to_decision_evidence(record) -> DecisionEvidence:
    return DecisionEvidence(
        evidence_id=record.evidence_id,
        decision_id=record.decision_id,
        evidence_type=record.evidence_type,
        evidence_reference=record.evidence_reference,
        summary=record.summary,
        created_at=record.created_at.isoformat(),
    )


def planner_request_for_session(
    session_id: str,
    request: PlannerPreviewRequest,
) -> PlannerRequest:
    runtime_session = runtime_session_service.get_session(session_id)
    available_tools = [
        to_available_tool(tool)
        for tool in tool_registry_service.list_tools()
    ]

    return PlannerRequest(
        task_id=runtime_session.task_id,
        session_id=runtime_session.id,
        objective=request.objective,
        available_tools=available_tools,
        context=request.context,
    )


def to_artifact(record: ArtifactRecord) -> Artifact:
    return Artifact(
        id=record.id,
        task_id=record.task_id,
        proposal_id=record.proposal_id,
        path=record.path,
        kind=record.kind,
        created_at=record.created_at.isoformat(),
        metadata=artifact_service.metadata_for(record),
    )


def to_runtime_task_artifact(
    record: RuntimeArtifactLinkRecord,
) -> RuntimeTaskArtifact:
    return RuntimeTaskArtifact(
        task_id=record.task_id,
        session_id=record.session_id,
        artifact_id=record.artifact_id,
        attached_at=record.created_at.isoformat(),
        artifact=to_artifact(artifact_service.get_artifact(record.artifact_id)),
    )


@router.get("/runtime/sessions")
def list_runtime_sessions(task_id: str | None = None) -> list[RuntimeSession]:
    return [
        to_runtime_session(record)
        for record in runtime_session_service.list_sessions(task_id=task_id)
    ]


@router.get("/runtime/sessions/{session_id}")
def get_runtime_session(session_id: str) -> RuntimeSession:
    try:
        return to_runtime_session(runtime_session_service.get_session(session_id))
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime/sessions/{session_id}/planning-context")
def get_planning_context(session_id: str) -> PlanningContext:
    try:
        return planning_context_service.build(session_id)
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime/sessions/{session_id}/cognitive-state")
def get_cognitive_state(session_id: str) -> CognitiveState:
    try:
        return cognitive_state_service.build(session_id)
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runtime/sessions/{session_id}/planner-preview")
async def planner_preview(
    session_id: str,
    request: PlannerPreviewRequest,
) -> PlannerResponse:
    try:
        planner_request = planner_input_builder_service.build(
            session_id,
            request.objective,
        )
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return await planner_service.plan(planner_request)


@router.post("/runtime/sessions/{session_id}/planner-proposal-preview")
async def planner_proposal_preview(
    session_id: str,
    request: PlannerPreviewRequest,
) -> PlannerProposalPreviewResponse:
    try:
        planner_request = planner_input_builder_service.build(
            session_id,
            request.objective,
        )
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    planner_response = await planner_service.plan(planner_request)
    governance_preview = governance_service.preview_decision()

    return PlannerProposalPreviewResponse(
        planner_response=planner_response,
        governance_preview=governance_preview,
        proposal_allowed=governance_preview["decision"] != "block",
    )


@router.post("/runtime/sessions/{session_id}/planner-recommendations")
async def create_planner_recommendation(
    session_id: str,
    request: PlannerPreviewRequest,
) -> PlannerRecommendationResponse:
    try:
        planner_request = planner_input_builder_service.build(
            session_id,
            request.objective,
        )
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    planner_response = await planner_service.plan(planner_request)
    governance_preview = governance_service.preview_decision()
    planning_context = PlanningContext.model_validate(
        planner_request.context["planning_context"]
    )
    recommendation = await planner_recommendation_service.create_recommendation_async(
        planner_request=planner_request,
        planner_response=planner_response,
        governance_preview=governance_preview,
        context_snapshot=planning_context_service.compact_snapshot(
            planning_context
        ),
    )

    return PlannerRecommendationResponse(
        recommendation=to_planner_recommendation(recommendation),
        planner_response=planner_response,
        governance_preview=governance_preview,
    )


@router.get("/runtime/sessions/{session_id}/planner-recommendations")
def list_planner_recommendations(
    session_id: str,
    status: PlannerRecommendationStatus | None = None,
) -> list[PlannerRecommendation]:
    try:
        runtime_session_service.get_session(session_id)
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [
        to_planner_recommendation(record)
        for record in planner_recommendation_service.list_recommendations(
            session_id,
            status=status.value if status is not None else None,
        )
    ]


@router.post("/runtime/sessions/{session_id}/decision-records")
def create_decision_record(
    session_id: str,
    request: DecisionRecordCreate,
) -> DecisionRecord:
    try:
        record = decision_record_service.create_decision_record(
            session_id=session_id,
            decision_type=request.decision_type,
            selected_entity_id=request.selected_entity_id,
            rationale=request.rationale,
        )
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlannerRecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DecisionRecordEntityMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return to_decision_record(record)


@router.get("/runtime/sessions/{session_id}/decision-records")
def list_decision_records(session_id: str) -> list[DecisionRecord]:
    try:
        runtime_session_service.get_session(session_id)
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [
        to_decision_record(record)
        for record in decision_record_service.list_decision_records(session_id)
    ]


@router.post("/decision-records/{decision_id}/evidence")
def create_decision_evidence(
    decision_id: str,
    request: DecisionEvidenceCreate,
) -> DecisionEvidence:
    try:
        record = decision_evidence_service.create_evidence(
            decision_id=decision_id,
            evidence_type=request.evidence_type,
            evidence_reference=request.evidence_reference,
            summary=request.summary,
        )
    except DecisionRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return to_decision_evidence(record)


@router.get("/decision-records/{decision_id}/evidence")
def list_decision_evidence(decision_id: str) -> list[DecisionEvidence]:
    try:
        decision_record_service.get_decision_record(decision_id)
    except DecisionRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [
        to_decision_evidence(record)
        for record in decision_evidence_service.list_evidence(decision_id)
    ]


@router.get(
    "/runtime/sessions/{session_id}/planner-recommendations/"
    "selection-preview"
)
def preview_planner_recommendation_selection(
    session_id: str,
) -> RecommendationSelectionPreview:
    try:
        runtime_session_service.get_session(session_id)
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return recommendation_selection_service.preview(session_id)


@router.post(
    "/runtime/sessions/{session_id}/planner-recommendations/"
    "{recommendation_id}/promote"
)
async def promote_planner_recommendation(
    session_id: str,
    recommendation_id: str,
) -> PlannerRecommendationPromotionResponse:
    try:
        runtime_session_service.get_session(session_id)
        recommendation_record = planner_recommendation_service.get_recommendation(
            recommendation_id
        )
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlannerRecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if recommendation_record.session_id != session_id:
        raise HTTPException(
            status_code=409,
            detail=(
                "Planner recommendation does not belong to runtime session: "
                f"{recommendation_id}"
            ),
        )
    if recommendation_record.status == PlannerRecommendationStatus.DISMISSED.value:
        raise HTTPException(
            status_code=409,
            detail=(
                "Dismissed planner recommendation cannot be promoted: "
                f"{recommendation_id}"
            ),
        )

    proposed_tool = planner_recommendation_service.proposed_tool_for(
        recommendation_record
    )
    context_snapshot = planner_recommendation_service.context_snapshot_for(
        recommendation_record
    )
    proposal_record = await proposal_service.create_proposal_async(
        title=f"Planner recommendation proposal: {recommendation_record.objective}",
        body=json.dumps(
            {
                "session_id": recommendation_record.session_id,
                "task_id": recommendation_record.task_id,
                "objective": recommendation_record.objective,
                "proposed_tool": proposed_tool,
                "planner_rationale": recommendation_record.rationale,
                "planner_confidence": recommendation_record.confidence,
                "governance_status": recommendation_record.governance_status,
                "source_recommendation_id": recommendation_record.id,
            },
            sort_keys=True,
        ),
        task_id=recommendation_record.task_id,
        source_type=ProposalSourceType.PLANNER_RECOMMENDATION.value,
        source_id=recommendation_record.id,
        source_context_snapshot=context_snapshot,
    )
    proposal = to_proposal(proposal_record)
    try:
        recommendation_record = planner_recommendation_service.mark_promoted(
            recommendation_record.id
        )
    except InvalidPlannerRecommendationTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await event_service.emit_event(
        event_type=EventType.PLANNER_RECOMMENDATION_PROMOTED,
        message=f"Planner recommendation promoted: {recommendation_record.id}",
        metadata={
            "recommendation_id": recommendation_record.id,
            "proposal_id": proposal.id,
            "task_id": recommendation_record.task_id,
            "session_id": recommendation_record.session_id,
            "proposed_tool": proposed_tool,
            "has_source_context_snapshot": context_snapshot is not None,
            "status": PlannerRecommendationStatus.PROMOTED.value,
        },
    )

    return PlannerRecommendationPromotionResponse(
        proposal=proposal,
        recommendation=to_planner_recommendation(recommendation_record),
    )


@router.post(
    "/runtime/sessions/{session_id}/planner-recommendations/"
    "{recommendation_id}/dismiss"
)
async def dismiss_planner_recommendation(
    session_id: str,
    recommendation_id: str,
) -> PlannerRecommendation:
    try:
        runtime_session_service.get_session(session_id)
        recommendation_record = planner_recommendation_service.get_recommendation(
            recommendation_id
        )
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlannerRecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if recommendation_record.session_id != session_id:
        raise HTTPException(
            status_code=409,
            detail=(
                "Planner recommendation does not belong to runtime session: "
                f"{recommendation_id}"
            ),
        )

    try:
        dismissed = await planner_recommendation_service.dismiss(
            recommendation_id
        )
    except InvalidPlannerRecommendationTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return to_planner_recommendation(dismissed)


@router.post("/runtime/sessions/{session_id}/planner-proposal")
async def planner_proposal(
    session_id: str,
    request: PlannerPreviewRequest,
) -> PlannerProposalResponse:
    try:
        planner_request = planner_request_for_session(session_id, request)
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    planner_response = await planner_service.plan(planner_request)
    proposed_tool = (
        planner_response.proposed_tool.model_dump(mode="json")
        if planner_response.proposed_tool is not None
        else None
    )
    proposal_record = await proposal_service.create_proposal_async(
        title=f"Planner proposal: {planner_request.objective}",
        body=json.dumps(
            {
                "session_id": planner_request.session_id,
                "task_id": planner_request.task_id,
                "objective": planner_request.objective,
                "context": planner_request.context,
                "proposed_tool": proposed_tool,
                "planner_rationale": planner_response.rationale,
                "planner_confidence": planner_response.confidence,
            },
            sort_keys=True,
        ),
        task_id=planner_request.task_id,
    )
    proposal = to_proposal(proposal_record)

    await event_service.emit_event(
        event_type=EventType.PLANNER_PROPOSAL_CREATED,
        message=f"Planner proposal created: {proposal.id}",
        metadata={
            "proposal_id": proposal.id,
            "session_id": planner_request.session_id,
            "task_id": planner_request.task_id,
            "objective": planner_request.objective,
            "proposed_tool_id": (
                planner_response.proposed_tool.id
                if planner_response.proposed_tool is not None
                else None
            ),
            "proposed_tool_name": (
                planner_response.proposed_tool.name
                if planner_response.proposed_tool is not None
                else None
            ),
            "planner_confidence": planner_response.confidence,
        },
    )

    return PlannerProposalResponse(
        proposal=proposal,
        planner_response=planner_response,
    )


@router.post("/runtime/sessions/{session_id}/work")
async def run_runtime_work(
    session_id: str,
    request: RuntimeWorkRequest,
) -> dict:
    try:
        return await work_loop_service.run_single_step(
            session_id=session_id,
            tool_name=request.tool_name,
            input_payload=request.input_payload,
        )
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolDisabledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/runtime/tasks")
def list_runtime_tasks() -> list[RuntimeExecution]:
    return [
        to_runtime_execution(record)
        for record in runtime_execution_service.list()
    ]


@router.get("/runtime/tasks/{task_id}")
def get_runtime_task(task_id: str) -> RuntimeExecution:
    try:
        return to_runtime_execution(runtime_execution_service.get(task_id))
    except RuntimeExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runtime/tasks/{task_id}/run")
async def run_task(task_id: str) -> dict:
    return await python_async_runtime.run_task(task_id)


@router.post("/runtime/tasks/{task_id}/artifacts/{artifact_id}")
def attach_runtime_artifact(
    task_id: str,
    artifact_id: str,
    session_id: str | None = None,
) -> RuntimeArtifactAttachment:
    try:
        runtime_artifact_service.attach_artifact(
            task_id=task_id,
            artifact_id=artifact_id,
            session_id=session_id,
        )
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeArtifactAlreadyAttachedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeArtifactSessionMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return RuntimeArtifactAttachment(
        task_id=task_id,
        artifact_id=artifact_id,
        session_id=session_id,
        attached=True,
    )


@router.get("/runtime/tasks/{task_id}/artifacts")
def list_runtime_task_artifacts(
    task_id: str,
    session_id: str | None = None,
) -> list[RuntimeTaskArtifact]:
    return [
        to_runtime_task_artifact(record)
        for record in runtime_artifact_service.list_task_artifacts(
            task_id,
            session_id=session_id,
        )
    ]


@router.post("/runtime/tasks/{task_id}/interrupt")
async def interrupt_task(task_id: str, request: RuntimeReasonRequest) -> dict:
    return await python_async_runtime.interrupt(task_id, request.reason)


@router.post("/runtime/tasks/{task_id}/stop")
async def stop_task(task_id: str, request: RuntimeReasonRequest) -> dict:
    return await python_async_runtime.stop(task_id, request.reason)
