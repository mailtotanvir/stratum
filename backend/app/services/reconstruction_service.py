from typing import Any

from app.db.schema import ProposalRecord, TaskRecord
from app.models.runtime_event import EventType, RuntimeEvent
from app.services.event_service import EventService, event_service
from app.services.planner_recommendation_service import (
    PlannerRecommendationService,
    planner_recommendation_service,
)
from app.services.proposal_service import ProposalService, proposal_service
from app.services.task_service import TaskService, task_service


TASK_LIFECYCLE_EVENTS = {
    EventType.TASK_CREATED.value,
    EventType.TASK_RUNNING.value,
    EventType.TASK_COMPLETED.value,
    EventType.TASK_FAILED.value,
}

PROPOSAL_LIFECYCLE_EVENTS = {
    EventType.PROPOSAL_GENERATED.value,
    EventType.PROPOSAL_RESOLVED.value,
}

PLANNER_RECOMMENDATION_EVENTS = {
    EventType.PLANNER_RECOMMENDATION_CREATED.value,
    EventType.PLANNER_RECOMMENDATION_PROMOTED.value,
    EventType.PLANNER_RECOMMENDATION_DISMISSED.value,
}


class ReconstructionService:
    def __init__(
        self,
        events: EventService | None = None,
        tasks: TaskService | None = None,
        proposals: ProposalService | None = None,
        recommendations: PlannerRecommendationService | None = None,
    ) -> None:
        self._events = events or event_service
        self._tasks = tasks or task_service
        self._proposals = proposals or proposal_service
        self._recommendations = recommendations or planner_recommendation_service

    def reconstruct_task_state(self, task_id: str) -> dict[str, Any]:
        states = self._reconstruct_states()
        return states.get(task_id, {"id": task_id, "found": False})

    def reconstruct_all_task_states(self) -> list[dict[str, Any]]:
        return list(self._reconstruct_states().values())

    def compare_task_record_to_events(self, task_id: str) -> dict[str, Any]:
        record = self._tasks.get_task(task_id)
        reconstructed = self.reconstruct_task_state(task_id)
        record_state = self._record_to_state(record)
        differences = self._differences(record_state, reconstructed)

        return {
            "task_id": task_id,
            "record": record_state,
            "reconstructed": reconstructed,
            "consistent": not differences,
            "differences": differences,
        }

    def task_consistency_health(self) -> dict[str, Any]:
        items = []

        for task in self._tasks.list_tasks():
            comparison = self.compare_task_record_to_events(task.id)
            items.append(
                {
                    "task_id": comparison["task_id"],
                    "consistent": comparison["consistent"],
                    "differences": comparison["differences"],
                }
            )

        consistent = sum(1 for item in items if item["consistent"])
        inconsistent = len(items) - consistent

        return {
            "checked": len(items),
            "consistent": consistent,
            "inconsistent": inconsistent,
            "items": items,
        }

    def reconstruct_proposal_state(self, proposal_id: str) -> dict[str, Any]:
        states = self._reconstruct_proposal_states()
        return states.get(proposal_id, {"id": proposal_id, "found": False})

    def reconstruct_all_proposal_states(self) -> list[dict[str, Any]]:
        return list(self._reconstruct_proposal_states().values())

    def compare_proposal_record_to_events(self, proposal_id: str) -> dict[str, Any]:
        record = self._proposals.get_proposal(proposal_id)
        reconstructed = self.reconstruct_proposal_state(proposal_id)
        record_state = self._proposal_record_to_state(record)
        differences = self._proposal_differences(record_state, reconstructed)

        return {
            "proposal_id": proposal_id,
            "record": record_state,
            "reconstructed": reconstructed,
            "consistent": not differences,
            "differences": differences,
        }

    def proposal_consistency_health(self) -> dict[str, Any]:
        items = []

        for proposal in self._proposals.list_proposals():
            comparison = self.compare_proposal_record_to_events(proposal.id)
            items.append(
                {
                    "proposal_id": comparison["proposal_id"],
                    "consistent": comparison["consistent"],
                    "differences": comparison["differences"],
                }
            )

        consistent = sum(1 for item in items if item["consistent"])
        inconsistent = len(items) - consistent

        return {
            "checked": len(items),
            "consistent": consistent,
            "inconsistent": inconsistent,
            "items": items,
        }

    def get_reconstructed_recommendations(
        self,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        recommendations = list(self._reconstruct_recommendation_states().values())
        if session_id is not None:
            recommendations = [
                recommendation
                for recommendation in recommendations
                if recommendation.get("session_id") == session_id
            ]
        return recommendations

    def get_recommendation_lineage(self, recommendation_id: str) -> dict[str, Any]:
        states = self._reconstruct_recommendation_states()
        return states.get(
            recommendation_id,
            {
                "recommendation_id": recommendation_id,
                "found": False,
                "promoted": False,
                "proposal_id": None,
            },
        )

    def recommendation_consistency_health(self) -> dict[str, Any]:
        states = self._reconstruct_recommendation_states()
        missing_promotion_references = [
            recommendation_id
            for recommendation_id, state in states.items()
            if state["promoted"] and not state["found"]
        ]
        missing_dismissal_references = [
            recommendation_id
            for recommendation_id, state in states.items()
            if state["dismissed_at"] is not None and not state["found"]
        ]
        lifecycle_issues = [
            issue
            for state in states.values()
            for issue in state["lifecycle_issues"]
        ]
        invalid_transition_count = sum(
            1
            for issue in lifecycle_issues
            if issue["issue_type"] == "invalid_status_transition"
        )
        missing_lifecycle_reference_count = sum(
            1
            for issue in lifecycle_issues
            if issue["issue_type"] == "missing_lifecycle_reference"
        )
        duplicate_terminal_event_count = sum(
            1
            for issue in lifecycle_issues
            if issue["issue_type"] == "duplicate_terminal_event"
        )
        missing_record_events: list[str] = []
        for record in self._recommendations.list_recommendations():
            if record.id not in states:
                missing_record_events.append(record.id)

        inconsistent = len(lifecycle_issues) + len(missing_record_events)
        return {
            "checked": len(states),
            "consistent": inconsistent == 0,
            "inconsistent": inconsistent,
            "missing_promotion_references": missing_promotion_references,
            "missing_dismissal_references": missing_dismissal_references,
            "missing_record_events": missing_record_events,
            "invalid_recommendation_status_transition_count": (
                invalid_transition_count
            ),
            "missing_recommendation_lifecycle_reference_count": (
                missing_lifecycle_reference_count
            ),
            "duplicate_recommendation_terminal_event_count": (
                duplicate_terminal_event_count
            ),
            "lifecycle_issues": lifecycle_issues,
        }

    def _reconstruct_states(self) -> dict[str, dict[str, Any]]:
        states: dict[str, dict[str, Any]] = {}

        for event in self._events.list_persisted_events():
            if event.type.value not in TASK_LIFECYCLE_EVENTS:
                continue

            task_id = event.metadata.get("task_id")
            if not isinstance(task_id, str):
                continue

            self._apply_event(states, task_id, event)

        return states

    def _reconstruct_proposal_states(self) -> dict[str, dict[str, Any]]:
        states: dict[str, dict[str, Any]] = {}

        for event in self._events.list_persisted_events():
            if event.type.value not in PROPOSAL_LIFECYCLE_EVENTS:
                continue

            proposal_id = event.metadata.get("proposal_id")
            if not isinstance(proposal_id, str):
                continue

            self._apply_proposal_event(states, proposal_id, event)

        return states

    def _reconstruct_recommendation_states(self) -> dict[str, dict[str, Any]]:
        states: dict[str, dict[str, Any]] = {}

        for event in self._events.list_persisted_events():
            if event.type.value not in PLANNER_RECOMMENDATION_EVENTS:
                continue

            recommendation_id = event.metadata.get("recommendation_id")
            if not isinstance(recommendation_id, str):
                continue

            self._apply_recommendation_event(states, recommendation_id, event)

        return states

    def _apply_event(
        self,
        states: dict[str, dict[str, Any]],
        task_id: str,
        event: RuntimeEvent,
    ) -> None:
        metadata = event.metadata
        state = states.setdefault(
            task_id,
            {
                "id": task_id,
                "found": True,
                "title": None,
                "status": None,
                "created_at": None,
                "completed_at": None,
                "summary": None,
            },
        )

        title = metadata.get("title")
        if isinstance(title, str):
            state["title"] = title

        summary = metadata.get("summary")
        if isinstance(summary, str):
            state["summary"] = summary

        created_at = metadata.get("created_at")
        if isinstance(created_at, str):
            state["created_at"] = created_at

        completed_at = metadata.get("completed_at")
        if isinstance(completed_at, str):
            state["completed_at"] = completed_at

        if event.type == EventType.TASK_CREATED:
            state["status"] = "created"
            if state["created_at"] is None:
                state["created_at"] = event.ts
        elif event.type == EventType.TASK_RUNNING:
            state["status"] = "running"
        elif event.type == EventType.TASK_COMPLETED:
            state["status"] = "completed"
            if state["completed_at"] is None:
                state["completed_at"] = event.ts
        elif event.type == EventType.TASK_FAILED:
            state["status"] = "failed"
            if state["completed_at"] is None:
                state["completed_at"] = event.ts

    def _apply_proposal_event(
        self,
        states: dict[str, dict[str, Any]],
        proposal_id: str,
        event: RuntimeEvent,
    ) -> None:
        metadata = event.metadata
        state = states.setdefault(
            proposal_id,
            {
                "id": proposal_id,
                "found": True,
                "task_id": None,
                "source_type": "manual",
                "source_id": None,
                "source_context_snapshot": None,
                "title": None,
                "body": None,
                "status": None,
                "created_at": None,
                "resolved_at": None,
                "decision": None,
            },
        )

        for field in [
            "task_id",
            "source_type",
            "source_id",
            "title",
            "body",
            "created_at",
            "resolved_at",
            "decision",
        ]:
            value = metadata.get(field)
            if isinstance(value, str):
                state[field] = value

        status = metadata.get("status")
        if isinstance(status, str):
            state["status"] = status

        source_context_snapshot = metadata.get("source_context_snapshot")
        if isinstance(source_context_snapshot, dict):
            state["source_context_snapshot"] = source_context_snapshot

        if event.type == EventType.PROPOSAL_GENERATED:
            state["status"] = "proposed"
            if state["created_at"] is None:
                state["created_at"] = event.ts
        elif event.type == EventType.PROPOSAL_RESOLVED:
            decision = state["decision"]
            if state["status"] not in {"approved", "rejected"}:
                if decision == "approve":
                    state["status"] = "approved"
                elif decision == "reject":
                    state["status"] = "rejected"
            if state["resolved_at"] is None:
                state["resolved_at"] = event.ts

    def _apply_recommendation_event(
        self,
        states: dict[str, dict[str, Any]],
        recommendation_id: str,
        event: RuntimeEvent,
    ) -> None:
        metadata = event.metadata
        state = states.setdefault(
            recommendation_id,
            {
                "recommendation_id": recommendation_id,
                "found": False,
                "task_id": None,
                "session_id": None,
                "objective": None,
                "proposed_tool": None,
                "rationale": None,
                "confidence": None,
                "governance_status": None,
                "status": "active",
                "context_snapshot": None,
                "created_at": None,
                "promoted_at": None,
                "dismissed_at": None,
                "terminal_status_reason": None,
                "promoted": False,
                "proposal_id": None,
                "lifecycle_issues": [],
            },
        )

        if event.type == EventType.PLANNER_RECOMMENDATION_CREATED:
            state["found"] = True
            for field in [
                "task_id",
                "session_id",
                "objective",
                "rationale",
                "governance_status",
                "created_at",
            ]:
                value = metadata.get(field)
                if isinstance(value, str):
                    state[field] = value

            proposed_tool = metadata.get("proposed_tool")
            if isinstance(proposed_tool, dict) or proposed_tool is None:
                state["proposed_tool"] = proposed_tool

            confidence = metadata.get("confidence")
            if isinstance(confidence, (int, float)):
                state["confidence"] = float(confidence)

            context_snapshot = metadata.get("context_snapshot")
            if isinstance(context_snapshot, dict):
                state["context_snapshot"] = context_snapshot
            status = metadata.get("status")
            if isinstance(status, str):
                state["status"] = status

            if state["created_at"] is None:
                state["created_at"] = event.ts

        elif event.type == EventType.PLANNER_RECOMMENDATION_PROMOTED:
            if not state["found"]:
                self._append_recommendation_issue(
                    state,
                    event,
                    issue_type="missing_lifecycle_reference",
                    previous_status=state["status"],
                )
            if state["status"] == "dismissed":
                self._append_recommendation_issue(
                    state,
                    event,
                    issue_type="invalid_status_transition",
                    previous_status="dismissed",
                )
                state["terminal_status_reason"] = "promoted_after_dismissed"
            state["promoted"] = True
            state["status"] = "promoted"
            if state["promoted_at"] is None:
                state["promoted_at"] = event.ts
            for field in ["task_id", "session_id"]:
                value = metadata.get(field)
                if isinstance(value, str):
                    state[field] = value
            proposal_id = metadata.get("proposal_id")
            if isinstance(proposal_id, str):
                state["proposal_id"] = proposal_id
            proposed_tool = metadata.get("proposed_tool")
            if isinstance(proposed_tool, dict) or proposed_tool is None:
                state["proposed_tool"] = proposed_tool
        elif event.type == EventType.PLANNER_RECOMMENDATION_DISMISSED:
            if not state["found"]:
                self._append_recommendation_issue(
                    state,
                    event,
                    issue_type="missing_lifecycle_reference",
                    previous_status=state["status"],
                )
            if state["status"] == "promoted":
                self._append_recommendation_issue(
                    state,
                    event,
                    issue_type="invalid_status_transition",
                    previous_status="promoted",
                )
                state["terminal_status_reason"] = "dismissed_after_promoted"
            elif state["status"] == "dismissed":
                self._append_recommendation_issue(
                    state,
                    event,
                    issue_type="duplicate_terminal_event",
                    previous_status="dismissed",
                )
                state["terminal_status_reason"] = "duplicate_dismissal"
            state["status"] = "dismissed"
            if state["dismissed_at"] is None:
                state["dismissed_at"] = event.ts
            for field in ["task_id", "session_id"]:
                value = metadata.get(field)
                if isinstance(value, str):
                    state[field] = value

    def _append_recommendation_issue(
        self,
        state: dict[str, Any],
        event: RuntimeEvent,
        issue_type: str,
        previous_status: str,
    ) -> None:
        state["lifecycle_issues"].append(
            {
                "issue_type": issue_type,
                "recommendation_id": state["recommendation_id"],
                "event_type": event.type.value,
                "event_id": event.id,
                "timestamp": event.ts,
                "previous_status": previous_status,
            }
        )

    def _record_to_state(self, record: TaskRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "found": True,
            "title": record.title,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
            "completed_at": (
                record.completed_at.isoformat()
                if record.completed_at is not None
                else None
            ),
            "summary": record.summary,
        }

    def _proposal_record_to_state(self, record: ProposalRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "found": True,
            "task_id": record.task_id,
            "source_type": record.source_type,
            "source_id": record.source_id,
            "source_context_snapshot": (
                self._proposals.source_context_snapshot_for(record)
            ),
            "title": record.title,
            "body": record.body,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
            "resolved_at": (
                record.resolved_at.isoformat()
                if record.resolved_at is not None
                else None
            ),
            "decision": record.decision,
        }

    def _differences(
        self,
        record: dict[str, Any],
        reconstructed: dict[str, Any],
    ) -> list[str]:
        fields = ["id", "title", "status", "created_at", "completed_at", "summary"]
        return [
            field
            for field in fields
            if record.get(field) != reconstructed.get(field)
        ]

    def _proposal_differences(
        self,
        record: dict[str, Any],
        reconstructed: dict[str, Any],
    ) -> list[str]:
        fields = [
            "id",
            "task_id",
            "source_type",
            "source_id",
            "source_context_snapshot",
            "title",
            "body",
            "status",
            "created_at",
            "resolved_at",
            "decision",
        ]
        return [
            field
            for field in fields
            if record.get(field) != reconstructed.get(field)
        ]


reconstruction_service = ReconstructionService()
