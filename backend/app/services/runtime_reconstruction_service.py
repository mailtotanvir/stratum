from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from app.models.artifact_lineage import ArtifactLineageRecord
from app.models.decision_lineage import DecisionLineageRecord
from app.models.runtime_event import EventType, RuntimeEvent, Severity
from app.models.runtime_health import RuntimeHealthStatus
from app.models.runtime_reconstruction import (
    RuntimeReconstructionArtifactSummary,
    RuntimeReconstructionDecisionSummary,
    RuntimeReconstructionEvaluationResultSummary,
    RuntimeReconstructionEvaluationSummary,
    RuntimeReconstructionHealthSummary,
    RuntimeReconstructionMetrics,
    RuntimeReconstructionProposalSummary,
    RuntimeReconstructionSessionSummary,
    RuntimeReconstructionTimelineItem,
    RuntimeReconstructionToolSummary,
    RuntimeReconstructionView,
)
from app.services.artifact_lineage_service import (
    ArtifactLineageService,
    artifact_lineage_service,
)
from app.services.decision_lineage_service import (
    DecisionLineageService,
    decision_lineage_service,
)
from app.services.event_service import EventService, event_service
from app.services.governance_audit_service import (
    GovernanceAuditService,
    governance_audit_service,
)
from app.services.runtime_health_service import runtime_health_service
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)


class HealthEvaluator(Protocol):
    def evaluate(self) -> RuntimeHealthStatus:
        """Evaluate current runtime health."""


MAJOR_RUNTIME_EVENT_TYPES = frozenset(
    {
        EventType.RUNTIME_SESSION_CREATED,
        EventType.RUNTIME_SESSION_RUNNING,
        EventType.RUNTIME_SESSION_COMPLETED,
        EventType.RUNTIME_SESSION_INTERRUPTED,
        EventType.RUNTIME_SESSION_STOPPED,
        EventType.RUNTIME_TASK_STARTED,
        EventType.RUNTIME_TASK_INTERRUPTED,
        EventType.RUNTIME_TASK_STOPPED,
        EventType.PLANNER_RECOMMENDATION_CREATED,
        EventType.PLANNER_RECOMMENDATION_PROMOTED,
        EventType.PLANNER_RECOMMENDATION_DISMISSED,
        EventType.DECISION_RECORD_CREATED,
        EventType.DECISION_EVIDENCE_CREATED,
        EventType.EVALUATION_CREATED,
        EventType.EVALUATION_RESULT_ADDED,
        EventType.PROPOSAL_GENERATED,
        EventType.PROPOSAL_RESOLVED,
        EventType.TOOL_EXECUTION_STARTED,
        EventType.TOOL_EXECUTION_COMPLETED,
        EventType.TOOL_EXECUTION_FAILED,
        EventType.ARTIFACT_CREATED,
        EventType.RUNTIME_ARTIFACT_ATTACHED,
        EventType.PROPOSAL_ARTIFACT_ATTACHED,
        EventType.WARNING,
        EventType.ERROR,
    }
)


class RuntimeReconstructionService:
    def __init__(
        self,
        events: EventService | None = None,
        sessions: RuntimeSessionService | None = None,
        decisions: DecisionLineageService | None = None,
        artifacts: ArtifactLineageService | None = None,
        governance: GovernanceAuditService | None = None,
        health: HealthEvaluator | None = None,
    ) -> None:
        self._events = events or event_service
        self._sessions = sessions or runtime_session_service
        self._decisions = decisions or decision_lineage_service
        self._artifacts = artifacts or artifact_lineage_service
        self._governance = governance or governance_audit_service
        self._health = health or runtime_health_service

    def list_sessions(self) -> list[RuntimeReconstructionSessionSummary]:
        summaries = [
            self._session_summary(session)
            for session in self._sessions.list_sessions()
        ]
        summaries.sort(
            key=lambda item: (
                item.last_activity_timestamp
                or datetime.min.replace(tzinfo=UTC),
                item.session_id,
            ),
            reverse=True,
        )
        return summaries

    def reconstruct(self, session_id: str) -> RuntimeReconstructionView:
        try:
            return self._reconstruct(session_id)
        except Exception as exc:
            self._emit(
                EventType.RUNTIME_RECONSTRUCTION_VIEW_FAILED,
                session_id,
                severity=Severity.ERROR,
                error_type=type(exc).__name__,
            )
            raise

    def _reconstruct(self, session_id: str) -> RuntimeReconstructionView:
        session = self._sessions.get_session(session_id)
        incomplete_reasons: list[str] = []
        session_events = self._session_events(session)
        decisions = self._safe_records(
            "decision_lineage_unavailable",
            self._decisions.list_records,
            incomplete_reasons,
        )
        artifacts = self._safe_records(
            "artifact_lineage_unavailable",
            self._artifacts.list_records,
            incomplete_reasons,
        )
        governance = self._safe_records(
            "governance_projection_unavailable",
            self._governance.list_records,
            incomplete_reasons,
        )
        health = self._safe_health(incomplete_reasons)
        if any(
            not isinstance(record, DecisionLineageRecord)
            for record in decisions
        ):
            incomplete_reasons.append("malformed_decision_lineage_data")
        if any(
            not isinstance(record, ArtifactLineageRecord)
            for record in artifacts
        ):
            incomplete_reasons.append("malformed_artifact_lineage_data")
        if any(
            not all(
                hasattr(record, field)
                for field in (
                    "decision_id",
                    "decision_type",
                    "outcome",
                    "occurred_at",
                    "evidence_count",
                )
            )
            for record in governance
        ):
            incomplete_reasons.append("malformed_governance_data")

        session_decisions = [
            record
            for record in decisions
            if isinstance(record, DecisionLineageRecord)
            and record.session_id == session_id
        ]
        decision_ids = {record.decision_id for record in session_decisions}
        session_artifacts = [
            record
            for record in artifacts
            if isinstance(record, ArtifactLineageRecord)
            and (
                record.session_id == session_id
                or record.decision_id in decision_ids
            )
        ]
        proposal_ids = {
            record.proposal_id
            for record in session_decisions
            if record.proposal_id is not None
        } | {
            record.proposal_id
            for record in session_artifacts
            if record.proposal_id is not None
        }

        decision_summaries = [
            self._decision_summary(record)
            for record in sorted(
                session_decisions,
                key=lambda item: (
                    item.selected_at,
                    item.decision_id,
                ),
            )
        ]
        artifact_summaries = [
            self._artifact_summary(record)
            for record in sorted(
                session_artifacts,
                key=lambda item: (
                    item.updated_at,
                    item.artifact_id,
                ),
            )
        ]
        governance_summaries = [
            RuntimeReconstructionDecisionSummary(
                decision_id=record.decision_id,
                decision_type=record.decision_type,
                outcome=record.outcome,
                occurred_at=record.occurred_at,
                evidence_count=record.evidence_count,
                complete=True,
            )
            for record in governance
            if (
                getattr(record, "session_id", None) == session_id
                or (
                    getattr(record, "session_id", None) is None
                    and getattr(record, "metadata", {}).get("task_id")
                    == session.task_id
                    and _within_window(
                        record.occurred_at,
                        session.created_at,
                        session.completed_at,
                    )
                )
            )
        ]
        proposals = self._proposal_summaries(
            session_events,
            proposal_ids,
        )
        evaluations = self._evaluation_summaries(session_events)
        tools = self._tool_summaries(session_events)
        timeline = self._timeline(session_events)

        lineage_incomplete = [
            f"decision_lineage_incomplete:{record.decision_id}"
            for record in session_decisions
            if bool(record.metadata.get("orphaned"))
        ] + [
            f"artifact_lineage_incomplete:{record.artifact_id}"
            for record in session_artifacts
            if record.lineage_status != "linked"
        ]
        incomplete_reasons.extend(lineage_incomplete)
        incomplete_reasons = sorted(set(incomplete_reasons))
        health_summary = self._health_summary(
            health,
            incomplete_reasons,
        )
        view = RuntimeReconstructionView(
            session_id=session.id,
            session_status=session.status,
            started_at=session.created_at,
            completed_at=session.completed_at,
            total_events=len(session_events),
            warnings_count=sum(
                event.severity == Severity.WARNING
                for event in session_events
            ),
            errors_count=sum(
                event.severity == Severity.ERROR
                for event in session_events
            ),
            critical_count=sum(
                event.severity == Severity.CRITICAL
                for event in session_events
            ),
            governance_decisions=governance_summaries,
            proposal_summaries=proposals,
            decision_lineage_summaries=decision_summaries,
            artifact_lineage_summaries=artifact_summaries,
            evaluation_summaries=evaluations,
            tool_execution_summaries=tools,
            health_consistency_status=health_summary,
            timeline=timeline,
            incomplete=bool(incomplete_reasons),
            incomplete_reasons=incomplete_reasons,
            diagnostics={
                "authoritative_source": "runtime_event_store",
                "projection_state_mutated": False,
            },
        )
        self._emit(
            (
                EventType.RUNTIME_RECONSTRUCTION_VIEW_INCOMPLETE
                if view.incomplete
                else EventType.RUNTIME_RECONSTRUCTION_VIEW_BUILT
            ),
            session_id,
            event_count=view.total_events,
            decision_count=len(decision_summaries),
            artifact_count=len(artifact_summaries),
            evaluation_count=len(evaluations),
            incomplete_reason_count=len(incomplete_reasons),
        )
        return view

    def timeline(
        self,
        session_id: str,
    ) -> list[RuntimeReconstructionTimelineItem]:
        session = self._sessions.get_session(session_id)
        return self._timeline(self._session_events(session))

    def metrics(self) -> RuntimeReconstructionMetrics:
        events = self._events.list_persisted_events()
        return RuntimeReconstructionMetrics(
            reconstruction_views_built_total=sum(
                event.type == EventType.RUNTIME_RECONSTRUCTION_VIEW_BUILT
                for event in events
            ),
            reconstruction_incomplete_views_total=sum(
                event.type
                == EventType.RUNTIME_RECONSTRUCTION_VIEW_INCOMPLETE
                for event in events
            ),
            reconstruction_failed_views_total=sum(
                event.type == EventType.RUNTIME_RECONSTRUCTION_VIEW_FAILED
                for event in events
            ),
            reconstructed_sessions_total=len(
                {
                    event.metadata.get("reconstructed_session_id")
                    for event in events
                    if event.type
                    in {
                        EventType.RUNTIME_RECONSTRUCTION_VIEW_BUILT,
                        EventType.RUNTIME_RECONSTRUCTION_VIEW_INCOMPLETE,
                    }
                    and isinstance(
                        event.metadata.get("reconstructed_session_id"),
                        str,
                    )
                }
            ),
        )

    def _session_summary(
        self,
        session: Any,
    ) -> RuntimeReconstructionSessionSummary:
        events = self._session_events(session)
        decision_count = sum(
            event.type == EventType.DECISION_RECORD_CREATED
            for event in events
        )
        artifact_count = len(
            {
                event.metadata.get("artifact_id")
                for event in events
                if event.type == EventType.ARTIFACT_CREATED
                and isinstance(event.metadata.get("artifact_id"), str)
            }
        )
        health_status = self._status_from_events(events)
        return RuntimeReconstructionSessionSummary(
            session_id=session.id,
            status=session.status,
            event_count=len(events),
            decision_count=decision_count,
            artifact_count=artifact_count,
            health_status=health_status,
            last_activity_timestamp=max(
                (_event_datetime(event) for event in events),
                default=session.created_at,
            ),
        )

    def _session_events(self, session: Any) -> list[RuntimeEvent]:
        started_at = _as_utc(session.created_at)
        completed_at = (
            _as_utc(session.completed_at)
            if session.completed_at is not None
            else None
        )
        events = [
            event
            for event in self._events.list_persisted_events()
            if self._belongs_to_session(
                event,
                session.id,
                session.task_id,
                started_at,
                completed_at,
            )
        ]
        return sorted(
            events,
            key=lambda event: (
                _event_datetime(event),
                event.id,
                event.type.value,
            ),
        )

    @staticmethod
    def _belongs_to_session(
        event: RuntimeEvent,
        session_id: str,
        task_id: str,
        started_at: datetime,
        completed_at: datetime | None,
    ) -> bool:
        metadata = event.metadata
        explicit_session_id = (
            metadata.get("session_id")
            or metadata.get("runtime_session_id")
        )
        if explicit_session_id is not None:
            return explicit_session_id == session_id
        if metadata.get("task_id") != task_id:
            return False
        occurred_at = _event_datetime(event)
        return occurred_at >= started_at and (
            completed_at is None or occurred_at <= completed_at
        )

    def _proposal_summaries(
        self,
        events: list[RuntimeEvent],
        linked_proposal_ids: set[str],
    ) -> list[RuntimeReconstructionProposalSummary]:
        states: dict[str, dict[str, Any]] = {}
        session_event_ids = {event.id for event in events}
        proposal_events = [
            event
            for event in self._events.list_persisted_events()
            if event.type
            in {
                EventType.PROPOSAL_GENERATED,
                EventType.PROPOSAL_RESOLVED,
            }
            and (
                event.id in session_event_ids
                or event.metadata.get("proposal_id")
                in linked_proposal_ids
            )
        ]
        for event in proposal_events:
            if event.type not in {
                EventType.PROPOSAL_GENERATED,
                EventType.PROPOSAL_RESOLVED,
            }:
                continue
            proposal_id = event.metadata.get("proposal_id")
            if not isinstance(proposal_id, str):
                continue
            state = states.setdefault(
                proposal_id,
                {
                    "status": "proposed",
                    "source_type": "manual",
                    "source_id": None,
                    "title": None,
                    "created_at": event.ts,
                    "resolved_at": None,
                },
            )
            for field in (
                "status",
                "source_type",
                "source_id",
                "title",
                "created_at",
                "resolved_at",
            ):
                value = event.metadata.get(field)
                if isinstance(value, str):
                    state[field] = value
        summaries = [
            RuntimeReconstructionProposalSummary(
                proposal_id=proposal_id,
                status=state["status"],
                source_type=state["source_type"],
                source_id=state["source_id"],
                title=state["title"],
                created_at=state["created_at"],
                resolved_at=state["resolved_at"],
            )
            for proposal_id, state in states.items()
        ]
        return sorted(
            summaries,
            key=lambda item: (item.created_at, item.proposal_id),
        )

    @staticmethod
    def _tool_summaries(
        events: list[RuntimeEvent],
    ) -> list[RuntimeReconstructionToolSummary]:
        states: dict[str, dict[str, Any]] = {}
        for event in events:
            if event.type not in {
                EventType.TOOL_INVOCATION_REQUESTED,
                EventType.TOOL_INVOCATION_RUNNING,
                EventType.TOOL_INVOCATION_COMPLETED,
                EventType.TOOL_INVOCATION_FAILED,
                EventType.TOOL_EXECUTION_STARTED,
                EventType.TOOL_EXECUTION_COMPLETED,
                EventType.TOOL_EXECUTION_FAILED,
            }:
                continue
            invocation_id = event.metadata.get("tool_invocation_id")
            if not isinstance(invocation_id, str):
                continue
            state = states.setdefault(
                invocation_id,
                {
                    "tool_id": None,
                    "tool_name": None,
                    "status": "requested",
                    "started_at": None,
                    "completed_at": None,
                    "artifact_ids": set(),
                },
            )
            for field in ("tool_id", "tool_name"):
                value = event.metadata.get(field)
                if isinstance(value, str):
                    state[field] = value
            if event.type in {
                EventType.TOOL_INVOCATION_RUNNING,
                EventType.TOOL_EXECUTION_STARTED,
            }:
                state["status"] = "running"
                state["started_at"] = state["started_at"] or event.ts
            elif event.type in {
                EventType.TOOL_INVOCATION_COMPLETED,
                EventType.TOOL_EXECUTION_COMPLETED,
            }:
                state["status"] = "completed"
                state["completed_at"] = (
                    event.metadata.get("completed_at") or event.ts
                )
            elif event.type in {
                EventType.TOOL_INVOCATION_FAILED,
                EventType.TOOL_EXECUTION_FAILED,
            }:
                state["status"] = "failed"
                state["completed_at"] = (
                    event.metadata.get("completed_at") or event.ts
                )
            output_payload = event.metadata.get("output_payload")
            if isinstance(output_payload, dict):
                artifact_ids = output_payload.get("artifacts")
                if isinstance(artifact_ids, list):
                    state["artifact_ids"].update(
                        artifact_id
                        for artifact_id in artifact_ids
                        if isinstance(artifact_id, str)
                    )
        summaries = [
            RuntimeReconstructionToolSummary(
                tool_invocation_id=invocation_id,
                tool_id=state["tool_id"],
                tool_name=state["tool_name"],
                status=state["status"],
                started_at=state["started_at"],
                completed_at=state["completed_at"],
                artifact_ids=sorted(state["artifact_ids"]),
            )
            for invocation_id, state in states.items()
        ]
        return sorted(
            summaries,
            key=lambda item: (
                item.started_at
                or item.completed_at
                or datetime.min.replace(tzinfo=UTC),
                item.tool_invocation_id,
            ),
        )

    @staticmethod
    def _evaluation_summaries(
        events: list[RuntimeEvent],
    ) -> list[RuntimeReconstructionEvaluationSummary]:
        states: dict[str, dict[str, Any]] = {}
        for event in events:
            if event.type not in {
                EventType.EVALUATION_CREATED,
                EventType.EVALUATION_RESULT_ADDED,
            }:
                continue
            evaluation_id = event.metadata.get("evaluation_id")
            if not isinstance(evaluation_id, str):
                continue
            state = states.setdefault(
                evaluation_id,
                {
                    "evaluation_type": None,
                    "status": None,
                    "created_at": event.ts,
                    "session_id": None,
                    "decision_id": None,
                    "artifact_id": None,
                    "results": [],
                },
            )
            if event.type == EventType.EVALUATION_CREATED:
                for field in (
                    "evaluation_type",
                    "status",
                    "created_at",
                    "session_id",
                    "decision_id",
                    "artifact_id",
                ):
                    value = event.metadata.get(field)
                    if isinstance(value, str):
                        state[field] = value
            elif event.type == EventType.EVALUATION_RESULT_ADDED:
                result_id = event.metadata.get("evaluation_result_id")
                dimension_id = event.metadata.get("dimension_id")
                rationale = event.metadata.get("rationale")
                score = event.metadata.get("score")
                if (
                    isinstance(result_id, str)
                    and isinstance(dimension_id, str)
                    and isinstance(rationale, str)
                    and isinstance(score, int | float)
                ):
                    state["results"].append(
                        RuntimeReconstructionEvaluationResultSummary(
                            evaluation_result_id=result_id,
                            dimension_id=dimension_id,
                            score=float(score),
                            rationale=rationale,
                            created_at=(
                                event.metadata.get("created_at")
                                or event.ts
                            ),
                        )
                    )
                for field in ("session_id", "decision_id", "artifact_id"):
                    value = event.metadata.get(field)
                    if isinstance(value, str) and state[field] is None:
                        state[field] = value

        summaries = []
        for evaluation_id, state in states.items():
            if not isinstance(state["evaluation_type"], str):
                continue
            if not isinstance(state["status"], str):
                continue
            summaries.append(
                RuntimeReconstructionEvaluationSummary(
                    evaluation_id=evaluation_id,
                    evaluation_type=state["evaluation_type"],
                    status=state["status"],
                    created_at=state["created_at"],
                    session_id=state["session_id"],
                    decision_id=state["decision_id"],
                    artifact_id=state["artifact_id"],
                    results=sorted(
                        state["results"],
                        key=lambda item: (
                            item.created_at,
                            item.evaluation_result_id,
                        ),
                    ),
                )
            )
        return sorted(
            summaries,
            key=lambda item: (item.created_at, item.evaluation_id),
        )

    @staticmethod
    def _timeline(
        events: list[RuntimeEvent],
    ) -> list[RuntimeReconstructionTimelineItem]:
        return [
            RuntimeReconstructionTimelineItem(
                event_id=event.id,
                occurred_at=event.ts,
                event_type=event.type.value,
                severity=event.severity.value,
                summary=event.message,
            )
            for event in events
            if event.type in MAJOR_RUNTIME_EVENT_TYPES
        ]

    @staticmethod
    def _decision_summary(
        record: DecisionLineageRecord,
    ) -> RuntimeReconstructionDecisionSummary:
        return RuntimeReconstructionDecisionSummary(
            decision_id=record.decision_id,
            decision_type=record.decision_type,
            outcome=record.outcome,
            occurred_at=record.selected_at,
            lineage_depth=record.lineage_depth,
            evidence_count=record.evidence_count,
            proposal_id=record.proposal_id,
            artifact_ids=record.related_artifact_ids,
            complete=not bool(record.metadata.get("orphaned")),
        )

    @staticmethod
    def _artifact_summary(
        record: ArtifactLineageRecord,
    ) -> RuntimeReconstructionArtifactSummary:
        return RuntimeReconstructionArtifactSummary(
            artifact_id=record.artifact_id,
            artifact_path=record.artifact_path,
            artifact_type=record.artifact_type,
            created_at=record.created_at,
            updated_at=record.updated_at,
            lineage_status=record.lineage_status,
            proposal_id=record.proposal_id,
            decision_id=record.decision_id,
            producing_tool_invocation_id=(
                record.producing_tool_invocation_id
            ),
            parent_artifact_ids=record.parent_artifact_ids,
        )

    def _safe_health(
        self,
        incomplete_reasons: list[str],
    ) -> RuntimeHealthStatus | None:
        try:
            return self._health.evaluate()
        except Exception:
            incomplete_reasons.append("runtime_health_unavailable")
            return None

    @staticmethod
    def _health_summary(
        health: RuntimeHealthStatus | None,
        incomplete_reasons: list[str],
    ) -> RuntimeReconstructionHealthSummary:
        if health is None:
            return RuntimeReconstructionHealthSummary(
                status="unhealthy",
                health_score=0,
                consistency_status="incomplete",
                finding_count=1,
                incomplete_reason_count=len(incomplete_reasons),
            )
        return RuntimeReconstructionHealthSummary(
            status=health.overall_status,
            health_score=health.health_score,
            consistency_status=(
                "incomplete" if incomplete_reasons else "consistent"
            ),
            finding_count=len(health.findings),
            incomplete_reason_count=len(incomplete_reasons),
        )

    @staticmethod
    def _status_from_events(
        events: list[RuntimeEvent],
    ) -> str:
        if any(event.severity == Severity.CRITICAL for event in events):
            return "unhealthy"
        if any(event.severity == Severity.ERROR for event in events):
            return "degraded"
        if any(event.severity == Severity.WARNING for event in events):
            return "warning"
        return "healthy"

    @staticmethod
    def _safe_records(
        reason: str,
        loader: Callable[[], list[Any]],
        incomplete_reasons: list[str],
    ) -> list[Any]:
        try:
            records = loader()
            return records if isinstance(records, list) else []
        except Exception:
            incomplete_reasons.append(reason)
            return []

    def _emit(
        self,
        event_type: EventType,
        session_id: str,
        *,
        severity: Severity = Severity.INFO,
        **metadata: Any,
    ) -> None:
        self._events.emit_event_sync(
            event_type=event_type,
            severity=severity,
            message=event_type.value.replace("_", " ").capitalize(),
            metadata={
                "reconstructed_session_id": session_id,
                **metadata,
            },
        )


def _event_datetime(event: RuntimeEvent) -> datetime:
    return _as_utc(datetime.fromisoformat(event.ts.replace("Z", "+00:00")))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _within_window(
    occurred_at: datetime,
    started_at: datetime,
    completed_at: datetime | None,
) -> bool:
    occurred = _as_utc(occurred_at)
    started = _as_utc(started_at)
    completed = (
        _as_utc(completed_at) if completed_at is not None else None
    )
    return occurred >= started and (
        completed is None or occurred <= completed
    )


runtime_reconstruction_service = RuntimeReconstructionService()
