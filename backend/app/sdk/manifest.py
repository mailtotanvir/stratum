from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ExtensionManifestDependency(BaseModel):
    extension_id: str = Field(min_length=1)
    minimum_version: str = Field(min_length=1)


class ExtensionManifest(BaseModel):
    model_config = ConfigDict()

    extension_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    author: str = Field(min_length=1)
    description: str | None = None
    kind: Literal[
        "provider",
        "tool",
        "execution-participant",
        "agent-adapter",
        "skill",
        "evaluation-pack",
        "memory-provider",
        "artifact-provider",
        "workspace-provider",
    ]
    capabilities: list[str] = Field(default_factory=list)
    runtime_compatibility: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[ExtensionManifestDependency] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    supported_protocols: list[str] = Field(default_factory=list)
    entrypoint: str | None = None
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "extension_id",
        "name",
        "version",
        "author",
        "description",
        "entrypoint",
    )
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def normalize_lists(self) -> "ExtensionManifest":
        self.capabilities = _unique_list(self.capabilities)
        self.permissions = _unique_list(self.permissions)
        self.supported_protocols = _unique_list(self.supported_protocols)
        return self


def _unique_list(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value.strip():
            raise ValueError("must not contain blank entries")
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
