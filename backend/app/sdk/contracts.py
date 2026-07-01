from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class CapabilityDescriptor(BaseModel):
    capability_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContractSchema(BaseModel):
    contract_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class ProviderContract(Protocol):
    provider_id: str
    display_name: str

    def capabilities(self) -> list[CapabilityDescriptor]: ...
    def health(self) -> dict[str, Any]: ...


@runtime_checkable
class ToolContract(Protocol):
    tool_id: str
    name: str

    def describe(self) -> dict[str, Any]: ...
    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class ExecutionParticipantContract(Protocol):
    participant_id: str
    name: str

    def capabilities(self) -> list[str]: ...
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class AgentAdapterContract(Protocol):
    adapter_id: str
    manifest: dict[str, Any]

    async def invoke(self, request: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class SkillContract(Protocol):
    skill_id: str
    name: str

    def manifest(self) -> dict[str, Any]: ...
    def steps(self) -> list[dict[str, Any]]: ...


@runtime_checkable
class MemoryProviderContract(Protocol):
    memory_provider_id: str

    def read(self, query: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class EvaluationProviderContract(Protocol):
    evaluation_provider_id: str

    def evaluate(self, subject: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class ArtifactProviderContract(Protocol):
    artifact_provider_id: str

    def list_artifacts(self) -> list[dict[str, Any]]: ...
    def get_artifact(self, artifact_id: str) -> dict[str, Any]: ...


@runtime_checkable
class WorkspaceProviderContract(Protocol):
    workspace_provider_id: str

    def list_workspaces(self) -> list[dict[str, Any]]: ...


ExtensionFactory = Callable[[dict[str, Any]], Any]

PUBLIC_CONTRACT_NAMES = (
    "provider",
    "tool",
    "execution-participant",
    "agent-adapter",
    "skill",
    "evaluation-pack",
)
