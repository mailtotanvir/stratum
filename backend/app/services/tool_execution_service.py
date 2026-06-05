from app.models.artifact import ArtifactKind
from app.models.runtime_event import EventType
from app.services.artifact_service import (
    ArtifactService,
    InvalidArtifactKindError,
    artifact_service,
)
from app.services.event_service import EventService, event_service
from app.services.governance_service import GovernanceService
from app.services.runtime_artifact_service import (
    RuntimeArtifactService,
    runtime_artifact_service,
)
from app.services.runtime_session_service import (
    RuntimeSessionService,
    runtime_session_service,
)
from app.services.tool_invocation_service import (
    ToolInvocationService,
    tool_invocation_service,
)
from app.services.tool_registry_service import (
    ToolRegistryService,
    tool_registry_service,
)
from app.tools.tool_execution_adapter import (
    MockToolExecutionAdapter,
    ToolExecutionAdapter,
)


class ToolDisabledError(RuntimeError):
    pass


class ToolExecutionService:
    def __init__(
        self,
        invocations: ToolInvocationService | None = None,
        tools: ToolRegistryService | None = None,
        events: EventService | None = None,
        adapter: ToolExecutionAdapter | None = None,
        governance: GovernanceService | None = None,
        artifacts: ArtifactService | None = None,
        runtime_artifacts: RuntimeArtifactService | None = None,
        sessions: RuntimeSessionService | None = None,
    ) -> None:
        self._invocations = invocations or tool_invocation_service
        self._tools = tools or tool_registry_service
        self._events = events or event_service
        self._adapter = adapter or MockToolExecutionAdapter()
        self._governance = governance or GovernanceService(self._events)
        self._artifacts = artifacts or artifact_service
        self._runtime_artifacts = runtime_artifacts or runtime_artifact_service
        self._sessions = sessions or runtime_session_service

    async def execute_invocation(self, invocation_id: str):
        invocation = self._invocations.get_invocation(invocation_id)
        tool = self._tools.get_tool(invocation.tool_id)
        if not tool.enabled:
            raise ToolDisabledError(f"Tool is disabled: {tool.id}")

        governance = self._governance_preview()
        if governance["decision"] == "block":
            await self._emit_governance_event(
                EventType.TOOL_EXECUTION_GOVERNANCE_BLOCKED,
                invocation,
                tool,
                governance,
                message=f"Tool execution governance blocked: {tool.name}",
            )
            failed = self._invocations.mark_failed_without_event(
                invocation.id,
                output_payload={
                    "governance": governance,
                },
            )
            await self._emit_invocation_terminal_event(
                EventType.TOOL_INVOCATION_FAILED,
                failed,
                message=f"Tool invocation failed: {tool.name}",
            )
            return failed

        if governance["decision"] == "warn":
            await self._emit_governance_event(
                EventType.TOOL_EXECUTION_GOVERNANCE_WARNING,
                invocation,
                tool,
                governance,
                message=f"Tool execution governance warning: {tool.name}",
            )

        await self._events.emit_event(
            event_type=EventType.TOOL_EXECUTION_STARTED,
            message=f"Tool execution started: {tool.name}",
            metadata={
                "tool_invocation_id": invocation.id,
                "session_id": invocation.session_id,
                "tool_id": invocation.tool_id,
                "tool_name": tool.name,
            },
        )

        result = await self._adapter.execute(
            invocation_id=invocation.id,
            tool_name=tool.name,
            input_payload=self._invocations.input_payload_for(invocation),
        )

        if result.success:
            try:
                artifact_ids = await self._persist_result_artifacts(
                    invocation,
                    result.artifacts,
                )
            except InvalidArtifactKindError as exc:
                failed = self._invocations.mark_failed_without_event(
                    invocation.id,
                    output_payload={
                        "error_message": str(exc),
                    },
                )
                await self._emit_invocation_terminal_event(
                    EventType.TOOL_INVOCATION_FAILED,
                    failed,
                    message=f"Tool invocation failed: {tool.name}",
                )
                await self._emit_execution_failed(tool, failed, str(exc))
                return failed

            output_payload = dict(result.output_payload or {})
            if artifact_ids:
                output_payload["artifacts"] = artifact_ids

            completed = self._invocations.mark_completed_without_event(
                invocation.id,
                output_payload=output_payload,
            )
        else:
            completed = self._invocations.mark_failed_without_event(
                invocation.id,
                output_payload={
                    "error_message": result.error_message,
                },
            )

        await self._events.emit_event(
            event_type=(
                EventType.TOOL_INVOCATION_COMPLETED
                if result.success
                else EventType.TOOL_INVOCATION_FAILED
            ),
            message=(
                f"Tool invocation completed: {tool.name}"
                if result.success
                else f"Tool invocation failed: {tool.name}"
            ),
            metadata=self._invocation_event_metadata(completed),
        )

        await self._events.emit_event(
            event_type=EventType.TOOL_EXECUTION_COMPLETED,
            message=f"Tool execution completed: {tool.name}",
            metadata={
                "tool_invocation_id": completed.id,
                "session_id": completed.session_id,
                "tool_id": completed.tool_id,
                "tool_name": tool.name,
                "success": result.success,
                "output_payload": self._invocations.output_payload_for(completed),
            },
        )
        return completed

    async def _persist_result_artifacts(
        self,
        invocation,
        artifact_declarations: list[dict],
    ) -> list[str]:
        for artifact in artifact_declarations:
            kind = artifact.get("kind", ArtifactKind.UNKNOWN.value)
            try:
                ArtifactKind(kind)
            except ValueError as exc:
                raise InvalidArtifactKindError(
                    f"Invalid artifact kind: {kind}"
                ) from exc

        runtime_session = self._sessions.get_session(invocation.session_id)
        artifact_ids: list[str] = []
        for artifact in artifact_declarations:
            record = self._artifacts.create_artifact_without_event(
                path=artifact["path"],
                kind=artifact.get("kind", ArtifactKind.UNKNOWN.value),
                task_id=runtime_session.task_id,
                metadata=artifact.get("metadata"),
            )
            artifact_ids.append(record.id)

            await self._events.emit_event(
                event_type=EventType.ARTIFACT_CREATED,
                message=f"Artifact registered: {record.path}",
                metadata=self._artifact_event_metadata(record),
            )

            link = self._runtime_artifacts.attach_artifact_without_event(
                task_id=runtime_session.task_id,
                artifact_id=record.id,
                session_id=invocation.session_id,
            )
            await self._events.emit_event(
                event_type=EventType.RUNTIME_ARTIFACT_ATTACHED,
                message=f"Runtime artifact attached: {record.id}",
                metadata=self._runtime_artifact_event_metadata(link),
            )

        return artifact_ids

    def _artifact_event_metadata(self, artifact) -> dict:
        metadata = {
            "artifact_id": artifact.id,
            "path": artifact.path,
            "kind": artifact.kind,
            "created_at": artifact.created_at.isoformat(),
        }
        if artifact.task_id is not None:
            metadata["task_id"] = artifact.task_id
        artifact_metadata = self._artifacts.metadata_for(artifact)
        if artifact_metadata is not None:
            metadata["metadata"] = artifact_metadata
        return metadata

    def _runtime_artifact_event_metadata(self, link) -> dict:
        metadata = {
            "runtime_artifact_link_id": link.id,
            "task_id": link.task_id,
            "artifact_id": link.artifact_id,
            "created_at": link.created_at.isoformat(),
        }
        if link.session_id is not None:
            metadata["session_id"] = link.session_id
        return metadata

    async def _emit_execution_failed(self, tool, invocation, error_message: str) -> None:
        await self._events.emit_event(
            event_type=EventType.TOOL_EXECUTION_FAILED,
            message=f"Tool execution failed: {tool.name}",
            metadata={
                "tool_invocation_id": invocation.id,
                "session_id": invocation.session_id,
                "tool_id": invocation.tool_id,
                "tool_name": tool.name,
                "success": False,
                "error_message": error_message,
                "output_payload": self._invocations.output_payload_for(invocation),
            },
        )

    def _governance_preview(self) -> dict:
        preview = self._governance.preview_decision()
        return {
            "decision": preview["decision"],
            "reasons": preview["reasons"],
        }

    async def _emit_governance_event(
        self,
        event_type: EventType,
        invocation,
        tool,
        governance: dict,
        message: str,
    ) -> None:
        await self._events.emit_event(
            event_type=event_type,
            message=message,
            metadata={
                "invocation_id": invocation.id,
                "tool_invocation_id": invocation.id,
                "tool_id": invocation.tool_id,
                "tool_name": tool.name,
                "session_id": invocation.session_id,
                "decision": governance["decision"],
                "reasons": governance["reasons"],
            },
        )

    async def _emit_invocation_terminal_event(
        self,
        event_type: EventType,
        invocation,
        message: str,
    ) -> None:
        await self._events.emit_event(
            event_type=event_type,
            message=message,
            metadata=self._invocation_event_metadata(invocation),
        )

    def _invocation_event_metadata(self, invocation) -> dict:
        metadata = {
            "tool_invocation_id": invocation.id,
            "session_id": invocation.session_id,
            "tool_id": invocation.tool_id,
            "status": invocation.status,
            "created_at": invocation.created_at.isoformat(),
        }
        output_payload = self._invocations.output_payload_for(invocation)
        if output_payload is not None:
            metadata["output_payload"] = output_payload
        if invocation.completed_at is not None:
            metadata["completed_at"] = invocation.completed_at.isoformat()
        return metadata


tool_execution_service = ToolExecutionService()
