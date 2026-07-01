from enum import StrEnum
from typing import Any

from pydantic import ConfigDict
from pydantic import BaseModel, Field, field_validator, model_validator


class ExecutionParticipantKind(StrEnum):
    HUMAN = "human"
    LOCAL_TOOL = "local_tool"
    PROVIDER = "provider"
    EXTERNAL_AGENT = "external_agent"
    MCP_SERVER = "mcp_server"
    A2A_AGENT = "a2a_agent"
    FUTURE_ADAPTER = "future_adapter"


class ExecutionParticipantLifecycle(StrEnum):
    REGISTERED = "registered"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    DISABLED = "disabled"


class ExecutionParticipantHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ExecutionRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutionParticipantContract(BaseModel):
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    approval_required: bool = False
    risk_level: ExecutionRiskLevel = ExecutionRiskLevel.LOW
    timeout_seconds: int = Field(default=300, ge=1)
    streaming_support: bool = False
    interrupt_support: bool = False
    retry_policy: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize(self) -> "ExecutionParticipantContract":
        self.inputs = _unique(self.inputs)
        self.outputs = _unique(self.outputs)
        self.artifacts = _unique(self.artifacts)
        return self


class ExecutionCapabilityManifest(BaseModel):
    capability_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    kind: ExecutionParticipantKind
    route_order: int = Field(ge=0)
    description: str | None = None
    operations: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    approval_required: bool = False
    risk_level: ExecutionRiskLevel = ExecutionRiskLevel.LOW
    streaming_support: bool = False
    interrupt_support: bool = False
    lifecycle: ExecutionParticipantLifecycle = ExecutionParticipantLifecycle.REGISTERED
    health: ExecutionParticipantHealth = ExecutionParticipantHealth.UNKNOWN
    availability: str = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("capability_id", "participant_id", "display_name")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def normalize(self) -> "ExecutionCapabilityManifest":
        self.operations = _unique(self.operations)
        self.inputs = _unique(self.inputs)
        self.outputs = _unique(self.outputs)
        self.artifacts = _unique(self.artifacts)
        return self


class ExecutionParticipantCapability(BaseModel):
    capability_id: str = Field(min_length=1)
    description: str | None = None
    operations: list[str] = Field(default_factory=list)


class ExecutionParticipant(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    participant_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    kind: ExecutionParticipantKind
    identity: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[ExecutionParticipantCapability] = Field(default_factory=list)
    lifecycle: ExecutionParticipantLifecycle = ExecutionParticipantLifecycle.REGISTERED
    health: ExecutionParticipantHealth = ExecutionParticipantHealth.UNKNOWN
    availability: str = "unknown"
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    version: str = "0.0.0"
    supported_operations: list[str] = Field(default_factory=list)
    contract: ExecutionParticipantContract = Field(default_factory=ExecutionParticipantContract)
    capability_manifest: list[ExecutionCapabilityManifest] = Field(
        default_factory=list,
        alias="capability_manifest",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("participant_id", "display_name", "version")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def normalize(self) -> "ExecutionParticipant":
        self.supported_operations = _unique(self.supported_operations)
        self.capability_manifest = sorted(
            self.capability_manifest,
            key=lambda manifest: (manifest.route_order, manifest.capability_id),
        )
        return self


class ExecutionCapabilityRouteRequest(BaseModel):
    capability_id: str = Field(min_length=1)
    preferred_kinds: list[ExecutionParticipantKind] = Field(default_factory=list)
    allow_unavailable: bool = False


class ExecutionParticipantRegistryDiagnostics(BaseModel):
    status: str
    total_participants: int
    kinds: dict[str, int]
    capabilities: dict[str, int] = Field(default_factory=dict)
    routing_policy: str = "deterministic-human-governed"
    registry_views: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionParticipantRegistry(BaseModel):
    participants: list[ExecutionParticipant]
    selected_participant_id: str | None = None
    eligible_participant_ids: list[str] = Field(default_factory=list)


class ExecutionInvocationState(StrEnum):
    CREATED = "created"
    VALIDATED = "validated"
    QUEUED = "queued"
    EXECUTING = "executing"
    WAITING = "waiting"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    INTERRUPTED = "interrupted"


class ExecutionInvocation(BaseModel):
    invocation_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    state: ExecutionInvocationState = ExecutionInvocationState.CREATED
    requested_by: str = "operator"
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionLifecycleActionRequest(BaseModel):
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value.strip():
            raise ValueError("must not contain blank entries")
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
