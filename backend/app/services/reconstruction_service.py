from typing import Any

from app.db.schema import ProposalRecord, TaskRecord
from app.models.runtime_event import EventType, RuntimeEvent
from app.services.event_service import EventService, event_service
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


class ReconstructionService:
    def __init__(
        self,
        events: EventService | None = None,
        tasks: TaskService | None = None,
        proposals: ProposalService | None = None,
    ) -> None:
        self._events = events or event_service
        self._tasks = tasks or task_service
        self._proposals = proposals or proposal_service

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
