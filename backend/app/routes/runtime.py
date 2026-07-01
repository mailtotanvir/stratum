import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
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
    PlannerRecommendation,
    PlannerRecommendationPromotionResponse,
    PlannerRecommendationResponse,
    PlannerRecommendationStatus,
    PlannerResponse,
    RecommendationSelectionPreview,
)
from app.models.planning_context import PlanningContext
from app.models.runtime_workspace import (
    RuntimeWorkspace,
    RuntimeWorkspaceSummary,
)
from app.models.runtime_workspace_binding import RuntimeWorkspaceBindingStatus
from app.models.projection import (
    ProjectionRegistryCatalog,
    ProjectionRegistryDetail,
    ProjectionRebuildRequest,
    ProjectionRebuildResult,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
    ProjectionSnapshotManifest,
    ProjectionSnapshotExport,
    ProjectionSnapshotExportRequest,
    ProjectionVerificationResult,
)
from app.models.projection_lineage import ProjectionLineage
from app.models.projection_lifecycle import (
    ProjectionLifecycleStatus,
    ProjectionRebuildHistory,
)
from app.models.projection_drift import (
    ProjectionDriftReport,
    ProjectionDriftResult,
)
from app.models.projection_replay import (
    ProjectionReplayRequest,
    ProjectionReplayResult,
)
from app.models.proposal import Proposal
from app.models.proposal import ProposalSourceType
from app.models.runtime_artifact import RuntimeArtifactAttachment, RuntimeTaskArtifact
from app.models.runtime_workspace_artifact import RuntimeWorkspaceArtifact
from app.models.runtime_execution import RuntimeExecution
from app.models.runtime_event import EventType
from app.models.runtime_session import RuntimeSession
from app.models.session_decision_projection import SessionDecisionProjection
from app.models.tool import Tool, ToolParameter
from app.runtime.projection_registry import (
    ProjectionTypeNotFoundError,
    projection_registry,
)
from app.runtime.projection_visibility import (
    PUBLIC_RUNTIME_PROJECTION_TYPES,
)
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
from app.services.projection_rebuild_service import (
    ProjectionRebuildError,
    ProjectionRebuildValidationError,
    projection_rebuild_service,
)
from app.services.projection_replay_service import (
    ProjectionReplayError,
    projection_replay_service,
)
from app.services.projection_registry_service import (
    ProjectionContractNotFoundError,
    projection_registry_service,
)
from app.services.projection_verification_service import (
    ProjectionVerificationError,
    projection_verification_service,
)
from app.services.projection_snapshot_manifest_service import (
    ProjectionManifestGenerationError,
    projection_snapshot_manifest_service,
)
from app.services.projection_snapshot_export_service import (
    ProjectionSnapshotExportError,
    projection_snapshot_export_service,
)
from app.services.projection_lineage_service import (
    ProjectionLineageGenerationError,
    projection_lineage_service,
)
from app.services.projection_lifecycle_service import (
    projection_lifecycle_service,
)
from app.services.provider_capability_registry_service import (
    provider_capability_registry_service,
)
from app.services.provider_health_service import provider_health_service
from app.services.projection_drift_service import (
    ProjectionDriftCheckError,
    projection_drift_service,
)
from app.services.recommendation_selection_service import (
    recommendation_selection_service,
)
from app.services.runtime_artifact_service import (
    RuntimeArtifactAlreadyAttachedError,
    RuntimeArtifactSessionMismatchError,
    runtime_artifact_service,
)
from app.services.runtime_workspace_artifact_service import (
    RuntimeWorkspaceArtifactService,
    runtime_workspace_artifact_service,
)
from app.services.runtime_workspace_binding_service import RuntimeWorkspaceBindingService
from app.services.runtime_execution_service import (
    RuntimeExecutionNotFoundError,
    runtime_execution_service,
)
from app.services.runtime_reconstruction_service import (
    runtime_reconstruction_service,
)
from app.services.runtime_workspace_service import (
    RuntimeWorkspaceService,
    runtime_workspace_service,
)
from app.services.runtime_session_service import (
    RuntimeSessionNotFoundError,
    runtime_session_service,
)
from app.services.session_decision_projection_builder_service import (
    session_decision_projection_builder_service,
)
from app.services.tool_execution_service import ToolDisabledError
from app.services.tool_registry_service import ToolNotFoundError, tool_registry_service

router = APIRouter()

BACKEND_VERSION = "0.1.0"


def get_runtime_workspace_service() -> RuntimeWorkspaceService:
    return runtime_workspace_service


class RuntimeReasonRequest(BaseModel):
    reason: str


class RuntimeWorkRequest(BaseModel):
    tool_name: str
    input_payload: dict | None = None


class RuntimeProjectionTypes(BaseModel):
    projection_types: list[str]
    schemas: list[ProjectionSchemaInfo]
    projections: list[ProjectionLifecycleStatus]


class RuntimeProjectionTypeDetail(BaseModel):
    projection_type: str
    schema_version: int
    registered: bool
    builder_name: str
    reconstruction: ProjectionReconstructionInfo
    source: str


class RuntimeSessionOverview(BaseModel):
    session_id: str
    status: str
    user_request: str | None = None
    workspace_id: str | None = None
    workspace_root_path: str | None = None
    provider: str | None = None
    model: str | None = None
    current_iteration: int | None = None
    max_iterations: int | None = None
    pending_approval: bool
    pending_approval_id: str | None = None
    last_tool: str | None = None
    final_answer: str | None = None
    error: str | None = None
    started_at: datetime
    updated_at: datetime


class RuntimeDashboardOverview(BaseModel):
    active_sessions: int
    pending_approvals: int
    completed_today: int
    failed_today: int
    stopped_today: int
    latest_sessions: list[RuntimeSessionOverview]


class RuntimeTimelineItem(BaseModel):
    timestamp: datetime
    event_type: str
    title: str
    summary: str
    severity: str
    payload: dict[str, Any]


class RuntimeStatusOverview(BaseModel):
    backend_version: str
    provider_status: str
    runtime_status: str
    registered_tools: list[str]
    registered_providers: list[str]
    event_count: int
    active_sessions: int


class RuntimeWorkspaceCreateRequest(BaseModel):
    name: str
    root_path: str


@router.get("/runtime/workspaces/binding", summary="Get active workspace binding status")
def get_runtime_workspace_binding(
    workspace: RuntimeWorkspaceService = Depends(get_runtime_workspace_service),
) -> RuntimeWorkspaceBindingStatus:
    return RuntimeWorkspaceBindingService(
        workspace=workspace,
        workspace_artifacts=RuntimeWorkspaceArtifactService(workspace=workspace),
    ).get_binding_status()


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


@router.get("/runtime/workspaces", summary="List runtime workspaces")
def list_runtime_workspaces(
    service: RuntimeWorkspaceService = Depends(get_runtime_workspace_service),
) -> list[RuntimeWorkspaceSummary]:
    return service.list_workspaces()


@router.get(
    "/runtime/workspaces/active",
    summary="Get active runtime workspace",
)
def get_active_runtime_workspace(
    service: RuntimeWorkspaceService = Depends(get_runtime_workspace_service),
) -> RuntimeWorkspace:
    return service.get_active_workspace()


@router.post("/runtime/workspaces", summary="Register runtime workspace")
def register_runtime_workspace(
    request: RuntimeWorkspaceCreateRequest,
    service: RuntimeWorkspaceService = Depends(get_runtime_workspace_service),
) -> RuntimeWorkspace:
    return service.register_workspace(request.name, request.root_path)


@router.post(
    "/runtime/workspaces/{workspace_id}/activate",
    summary="Activate runtime workspace",
)
def activate_runtime_workspace(
    workspace_id: str,
    service: RuntimeWorkspaceService = Depends(get_runtime_workspace_service),
) -> RuntimeWorkspace:
    return service.set_active_workspace(workspace_id)


def _parse_iso_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=None)


def _session_events(session_id: str) -> list[Any]:
    session = runtime_session_service.get_session(session_id)
    started_at = _naive(_parse_iso_datetime(session.created_at))
    completed_at = _naive(_parse_iso_datetime(session.completed_at))
    events = []
    for event in event_service.list_persisted_events():
        metadata = event.metadata
        explicit_session_id = metadata.get("session_id") or metadata.get(
            "runtime_session_id"
        )
        if explicit_session_id is not None:
            if explicit_session_id != session_id:
                continue
        elif metadata.get("task_id") != session.task_id:
            continue
        occurred_at = _naive(datetime.fromisoformat(event.ts))
        if started_at is not None and occurred_at < started_at:
            continue
        if completed_at is not None and occurred_at > completed_at:
            continue
        events.append(event)
    return sorted(events, key=lambda item: (item.ts, item.id, item.type.value))


def _session_state(session_id: str) -> dict[str, Any]:
    state: dict[str, Any] = {
        "user_request": None,
        "workspace_id": None,
        "workspace_root_path": None,
        "provider": None,
        "model": None,
        "current_iteration": None,
        "max_iterations": None,
        "pending_approval": False,
        "pending_approval_id": None,
        "approval_history": [],
        "interrupted": False,
        "interrupt_reason": None,
        "last_tool": None,
        "final_answer": None,
        "error": None,
    }
    for event in _session_events(session_id):
        metadata = event.metadata
        if event.type == EventType.AGENT_LOOP_STARTED:
            state["user_request"] = metadata.get("user_request")
            state["workspace_id"] = metadata.get("workspace_id")
            state["workspace_root_path"] = metadata.get(
                "workspace_root_path"
            )
            state["provider"] = metadata.get("provider_id")
            state["model"] = metadata.get("model")
            state["max_iterations"] = metadata.get("max_iterations")
        if isinstance(metadata.get("iteration"), int):
            state["current_iteration"] = metadata["iteration"]
        if isinstance(metadata.get("tool"), str):
            state["last_tool"] = metadata["tool"]
        if event.type == EventType.AGENT_LOOP_APPROVAL_REQUESTED:
            state["pending_approval"] = True
            state["pending_approval_id"] = metadata.get("approval_id")
            state["approval_history"].append(
                {
                    "approval_id": metadata.get("approval_id"),
                    "status": metadata.get("status"),
                    "iteration": metadata.get("iteration"),
                    "tool": metadata.get("tool"),
                    "arguments": metadata.get("arguments", {}),
                    "message": event.message,
                    "timestamp": event.ts,
                }
            )
        elif event.type == EventType.AGENT_LOOP_APPROVAL_RESPONDED:
            state["pending_approval"] = False
            state["approval_history"].append(
                {
                    "approval_id": metadata.get("approval_id"),
                    "status": metadata.get("status"),
                    "reason": metadata.get("reason"),
                    "message": event.message,
                    "timestamp": event.ts,
                }
            )
        elif event.type == EventType.AGENT_LOOP_APPROVAL_RESUMED:
            state["approval_history"].append(
                {
                    "approval_id": metadata.get("approval_id"),
                    "status": "resumed",
                    "iteration": metadata.get("iteration"),
                    "tool": metadata.get("tool"),
                    "message": event.message,
                    "timestamp": event.ts,
                }
            )
        elif event.type == EventType.AGENT_LOOP_APPROVAL_RESUME_REJECTED:
            state["approval_history"].append(
                {
                    "approval_id": metadata.get("approval_id"),
                    "status": "resume_rejected",
                    "reason": metadata.get("reason"),
                    "message": event.message,
                    "timestamp": event.ts,
                }
            )
        elif event.type == EventType.AGENT_LOOP_APPROVAL_CONTINUE_STARTED:
            state["approval_history"].append(
                {
                    "approval_id": metadata.get("approval_id"),
                    "status": "continue_started",
                    "iteration": metadata.get("iteration"),
                    "tool": metadata.get("tool"),
                    "message": event.message,
                    "timestamp": event.ts,
                }
            )
        elif event.type == EventType.AGENT_LOOP_COMPLETED:
            state["final_answer"] = metadata.get("final_answer")
            state["pending_approval"] = False
            state["pending_approval_id"] = None
            state["interrupted"] = False
        elif event.type in {
            EventType.AGENT_LOOP_FAILED,
            EventType.AGENT_LOOP_STOPPED,
        }:
            state["error"] = metadata.get("error") or event.message
            state["pending_approval"] = False
            state["pending_approval_id"] = None
        elif event.type == EventType.RUNTIME_SESSION_INTERRUPTED:
            state["interrupted"] = True
            state["interrupt_reason"] = metadata.get("reason")
    return state


def _session_overview(session_id: str) -> RuntimeSessionOverview:
    session = runtime_session_service.get_session(session_id)
    state = _session_state(session_id)
    return RuntimeSessionOverview(
        session_id=session.id,
        status=session.status,
        user_request=state["user_request"],
        workspace_id=state["workspace_id"],
        workspace_root_path=state["workspace_root_path"],
        provider=state["provider"],
        model=state["model"],
        current_iteration=state["current_iteration"],
        max_iterations=state["max_iterations"],
        pending_approval=bool(state["pending_approval"]),
        pending_approval_id=state["pending_approval_id"],
        last_tool=state["last_tool"],
        final_answer=state["final_answer"],
        error=state["error"],
        started_at=session.created_at,
        updated_at=session.completed_at or session.created_at,
    )


def _timeline_item(event) -> RuntimeTimelineItem:
    title_map = {
        EventType.AGENT_LOOP_STARTED: "Agent loop started",
        EventType.AGENT_LOOP_PROVIDER_REQUESTED: "Provider requested",
        EventType.AGENT_LOOP_PROVIDER_COMPLETED: "Provider completed",
        EventType.AGENT_LOOP_TOOL_SELECTED: "Tool selected",
        EventType.AGENT_LOOP_TOOL_COMPLETED: "Tool completed",
        EventType.AGENT_LOOP_APPROVAL_REQUESTED: "Approval requested",
        EventType.AGENT_LOOP_APPROVAL_RESPONDED: "Approval responded",
        EventType.AGENT_LOOP_APPROVAL_RESUMED: "Approval resumed",
        EventType.AGENT_LOOP_APPROVAL_CONTINUE_STARTED: "Approval continue started",
        EventType.AGENT_LOOP_COMPLETED: "Agent loop completed",
        EventType.AGENT_LOOP_FAILED: "Agent loop failed",
        EventType.AGENT_LOOP_STOPPED: "Agent loop stopped",
        EventType.RUNTIME_SESSION_RUNNING: "Session running",
        EventType.RUNTIME_SESSION_COMPLETED: "Session completed",
        EventType.RUNTIME_SESSION_INTERRUPTED: "Session interrupted",
        EventType.RUNTIME_SESSION_STOPPED: "Session stopped",
    }
    payload = {
        key: value
        for key, value in event.metadata.items()
        if key not in {"internal", "provider_response", "raw_output"}
    }
    return RuntimeTimelineItem(
        timestamp=event.ts,
        event_type=event.type.value,
        title=title_map.get(
            event.type, event.type.value.replace("_", " ").title()
        ),
        summary=event.message,
        severity=event.severity.value,
        payload=payload,
    )


def _dashboard_overview() -> RuntimeDashboardOverview:
    sessions = runtime_session_service.list_sessions()
    today = datetime.now().date()
    active_sessions = sum(
        session.status in {"created", "running"} for session in sessions
    )
    completed_today = sum(
        session.status == "completed"
        and (completed := _parse_iso_datetime(session.completed_at)) is not None
        and completed.date() == today
        for session in sessions
    )
    failed_today = sum(
        session.status == "interrupted"
        and (completed := _parse_iso_datetime(session.completed_at)) is not None
        and completed.date() == today
        for session in sessions
    )
    stopped_today = sum(
        session.status == "stopped"
        and (completed := _parse_iso_datetime(session.completed_at)) is not None
        and completed.date() == today
        for session in sessions
    )
    latest_sessions = [_session_overview(session.id) for session in sessions[:25]]
    pending_approvals = sum(
        1 for session in sessions if _session_state(session.id)["pending_approval"]
    )
    return RuntimeDashboardOverview(
        active_sessions=active_sessions,
        pending_approvals=pending_approvals,
        completed_today=completed_today,
        failed_today=failed_today,
        stopped_today=stopped_today,
        latest_sessions=latest_sessions,
    )


@router.get("/runtime/session/{session_id}/governance")
def get_runtime_session_governance(session_id: str) -> dict[str, Any]:
    try:
        session = runtime_session_service.get_session(session_id)
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    state = _session_state(session.id)
    events = _session_events(session.id)
    approval_events = [
        _timeline_item(event).model_dump(mode="json")
        for event in events
        if event.type
        in {
            EventType.AGENT_LOOP_APPROVAL_REQUESTED,
            EventType.AGENT_LOOP_APPROVAL_RESPONDED,
            EventType.AGENT_LOOP_APPROVAL_RESUMED,
            EventType.AGENT_LOOP_APPROVAL_RESUME_REJECTED,
            EventType.AGENT_LOOP_APPROVAL_CONTINUE_STARTED,
        }
    ]
    return {
        "session_id": session.id,
        "pending_approval": bool(state["pending_approval"]),
        "pending_approval_id": state["pending_approval_id"],
        "approval_history": state["approval_history"],
        "interrupted": bool(state["interrupted"]),
        "interrupt_reason": state["interrupt_reason"],
        "approval_events": approval_events,
        "decision_evidence": [
            event.to_dict()
            for event in events
            if event.type
            in {
                EventType.DECISION_RECORD_CREATED,
                EventType.DECISION_EVIDENCE_CREATED,
                EventType.PROPOSAL_GENERATED,
                EventType.PROPOSAL_RESOLVED,
            }
        ],
    }


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


@router.get("/runtime/projection-diagnostics")
@router.get("/runtime/projections")
def list_runtime_projection_types() -> RuntimeProjectionTypes:
    projection_types = [
        projection_type
        for projection_type in PUBLIC_RUNTIME_PROJECTION_TYPES
        if projection_type in projection_registry.list_projection_types()
    ]
    schemas = [
        projection_registry.get_schema(projection_type)
        for projection_type in projection_types
    ]
    projections = [
        status
        for status in projection_lifecycle_service.projection_statuses()
        if status.projection_name in projection_types
    ]
    event_service.emit_event_sync(
        event_type=EventType.PROJECTION_REGISTRY_INSPECTED,
        message="Projection registry inspected",
        metadata={
            "projection_type_count": len(projection_types),
            "projection_types": projection_types,
            "source": "projection_registry",
        },
    )
    return RuntimeProjectionTypes(
        projection_types=projection_types,
        schemas=schemas,
        projections=projections,
    )


@router.get("/runtime/projections/history")
def get_runtime_projection_rebuild_history() -> ProjectionRebuildHistory:
    return projection_lifecycle_service.rebuild_history()


@router.get("/runtime/projections/replay/preview")
def preview_runtime_projection_replay(
    projection_name: str,
    event_id_start: int | None = Query(default=None, ge=1),
    event_id_end: int | None = Query(default=None, ge=1),
) -> ProjectionReplayResult:
    if (
        event_id_start is not None
        and event_id_end is not None
        and event_id_start > event_id_end
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "event_id_start must be less than or equal to event_id_end"
            ),
        )
    request = ProjectionReplayRequest(
        projection_name=projection_name,
        event_id_start=event_id_start,
        event_id_end=event_id_end,
    )
    try:
        return projection_replay_service.preview(request)
    except ProjectionTypeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectionReplayError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": str(exc),
                "result": exc.result.model_dump(mode="json"),
            },
        ) from exc


@router.post("/runtime/projections/replay")
def replay_runtime_projection(
    request: ProjectionReplayRequest,
) -> ProjectionReplayResult:
    try:
        return projection_replay_service.replay(request)
    except ProjectionTypeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectionReplayError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": str(exc),
                "result": exc.result.model_dump(mode="json"),
            },
        ) from exc


@router.get("/runtime/projections/drift")
def get_runtime_projection_drift() -> ProjectionDriftReport:
    return projection_drift_service.check_all()


@router.get("/runtime/projections/{projection_name}/drift")
def get_runtime_projection_drift_detail(
    projection_name: str,
) -> ProjectionDriftResult:
    try:
        return projection_drift_service.check_projection(projection_name)
    except ProjectionTypeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectionDriftCheckError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": str(exc),
                "result": exc.result.model_dump(mode="json"),
            },
        ) from exc


@router.get("/runtime/projections/registry")
def get_runtime_projection_registry() -> ProjectionRegistryCatalog:
    return projection_registry_service.list_registry()


@router.get("/runtime/projections/registry/{projection_name}")
def get_runtime_projection_registry_detail(
    projection_name: str,
) -> ProjectionRegistryDetail:
    try:
        return projection_registry_service.get(projection_name)
    except ProjectionContractNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime/projections/{projection_type}")
def get_runtime_projection_type(
    projection_type: str,
) -> RuntimeProjectionTypeDetail:
    try:
        schema = projection_registry.get_schema(projection_type)
    except ProjectionTypeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return RuntimeProjectionTypeDetail(
        projection_type=projection_type,
        schema_version=schema.schema_version,
        registered=True,
        builder_name=schema.builder_name,
        reconstruction=schema.reconstruction,
        source="projection_registry",
    )


@router.post("/runtime/projections/{projection_type}/rebuild")
def rebuild_runtime_projection(
    projection_type: str,
    request: ProjectionRebuildRequest,
) -> ProjectionRebuildResult:
    try:
        return projection_rebuild_service.rebuild(
            projection_type,
            request.source,
        )
    except ProjectionTypeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectionRebuildValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "diagnostics": [
                    diagnostic.model_dump(mode="json")
                    for diagnostic in exc.diagnostics
                ],
            },
        ) from exc
    except ProjectionRebuildError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": str(exc),
                "diagnostics": [
                    diagnostic.model_dump(mode="json")
                    for diagnostic in exc.diagnostics
                ],
            },
        ) from exc


@router.get("/projections/{projection_type}/verify")
@router.get("/runtime/projections/{projection_type}/verify")
def verify_runtime_projection(
    projection_type: str,
    source: str,
) -> ProjectionVerificationResult:
    try:
        return projection_verification_service.verify(
            projection_type,
            source,
        )
    except ProjectionTypeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectionVerificationError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": str(exc),
                "diagnostics": [
                    diagnostic.model_dump(mode="json")
                    for diagnostic in exc.diagnostics
                ],
            },
        ) from exc


@router.get("/projections/{projection_type}/manifest")
@router.get("/runtime/projections/{projection_type}/manifest")
def get_projection_manifest(
    projection_type: str,
    source: str,
) -> ProjectionSnapshotManifest:
    try:
        return projection_snapshot_manifest_service.current_manifest(
            projection_type,
            source,
        )
    except ProjectionTypeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectionManifestGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/projections/{projection_type}/lineage")
@router.get("/runtime/projections/{projection_type}/lineage")
def get_projection_lineage(
    projection_type: str,
    source: str,
) -> ProjectionLineage:
    try:
        return projection_lineage_service.generate(
            projection_type,
            source,
        )
    except ProjectionTypeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectionLineageGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/projections/{projection_type}/export")
@router.post("/runtime/projections/{projection_type}/export")
def export_projection_snapshot(
    projection_type: str,
    request: ProjectionSnapshotExportRequest,
) -> ProjectionSnapshotExport:
    try:
        return projection_snapshot_export_service.export(
            projection_type,
            request.source,
            verify=request.verify,
            include_lineage=request.include_lineage,
        )
    except ProjectionTypeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectionSnapshotExportError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": str(exc),
                "diagnostics": [
                    diagnostic.model_dump(mode="json")
                    for diagnostic in exc.diagnostics
                ],
            },
        ) from exc


@router.get("/runtime/sessions/{session_id}")
def get_runtime_session(session_id: str) -> RuntimeSession:
    try:
        return to_runtime_session(runtime_session_service.get_session(session_id))
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime/session/{session_id}")
def get_runtime_session_overview(session_id: str) -> RuntimeSessionOverview:
    try:
        return _session_overview(session_id)
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime/session/{session_id}/summary")
def get_runtime_session_summary(session_id: str) -> RuntimeSessionOverview:
    try:
        return _session_overview(session_id)
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime/dashboard")
def get_runtime_dashboard() -> RuntimeDashboardOverview:
    return _dashboard_overview()


@router.get("/runtime/session/{session_id}/timeline")
def get_runtime_session_timeline(session_id: str) -> list[RuntimeTimelineItem]:
    try:
        return [_timeline_item(event) for event in _session_events(session_id)]
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runtime/status")
def get_runtime_status() -> RuntimeStatusOverview:
    sessions = runtime_session_service.list_sessions()
    return RuntimeStatusOverview(
        backend_version=BACKEND_VERSION,
        provider_status=provider_health_service.health().status,
        runtime_status="healthy",
        registered_tools=[tool.name for tool in tool_registry_service.list_tools()],
        registered_providers=provider_capability_registry_service.list_providers(),
        event_count=len(event_service.list_persisted_events()),
        active_sessions=sum(
            session.status in {"created", "running"} for session in sessions
        ),
    )


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


@router.get("/runtime/sessions/{session_id}/decision-projections")
def get_decision_projections(
    session_id: str,
) -> SessionDecisionProjection:
    try:
        return session_decision_projection_builder_service.build(session_id)
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runtime/sessions/{session_id}/planner-preview")
async def planner_preview(
    session_id: str,
    request: PlannerPreviewRequest,
) -> PlannerResponse:
    try:
        planner_request = await planner_input_builder_service.build(
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
        planner_request = await planner_input_builder_service.build(
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
        planner_request = await planner_input_builder_service.build(
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
async def preview_planner_recommendation_selection(
    session_id: str,
) -> RecommendationSelectionPreview:
    try:
        planner_request = await planner_input_builder_service.build(
            session_id,
            "Preview planner recommendation selection",
        )
    except RuntimeSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return recommendation_selection_service.preview(
        session_id,
        snapshot_metadata=planner_request.snapshot_metadata,
    )


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
        planner_request = await planner_input_builder_service.build(
            session_id,
            request.objective,
        )
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


@router.get("/runtime/workspaces/{workspace_id}/artifacts")
def list_runtime_workspace_artifacts(
    workspace_id: str,
    service: RuntimeWorkspaceService = Depends(get_runtime_workspace_service),
) -> list[RuntimeWorkspaceArtifact]:
    return runtime_workspace_artifact_service.__class__(
        service
    ).list_workspace_artifacts(workspace_id)


@router.get("/runtime/sessions/{session_id}/artifacts")
def list_runtime_session_artifacts(
    session_id: str,
    service: RuntimeWorkspaceService = Depends(get_runtime_workspace_service),
) -> list[RuntimeWorkspaceArtifact]:
    return runtime_workspace_artifact_service.__class__(
        service
    ).list_session_artifacts(session_id)


@router.post("/runtime/tasks/{task_id}/interrupt")
async def interrupt_task(task_id: str, request: RuntimeReasonRequest) -> dict:
    return await python_async_runtime.interrupt(task_id, request.reason)


@router.post("/runtime/tasks/{task_id}/stop")
async def stop_task(task_id: str, request: RuntimeReasonRequest) -> dict:
    return await python_async_runtime.stop(task_id, request.reason)
