"""Universal AI adapter contract.

The provider layer answers: "How do I communicate with this AI system?"
The runtime answers: "What do I do with the AI result?" This module defines
the boundary between the two. The runtime core never imports provider SDKs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AIMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class AIRequest:
    """A single model invocation request."""

    model: str
    messages: tuple[AIMessage, ...]
    temperature: float = 0.0
    max_tokens: int = 4096
    # Ask the provider for a JSON-object response (where supported).
    response_json: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AIUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class AIResponse:
    """A real model response, normalized."""

    request_id: str | None
    model: str
    content: str
    finish_reason: str | None = None
    usage: AIUsage = field(default_factory=AIUsage)
    latency_ms: int = 0


class AIAdapter(Protocol):
    async def generate(self, request: AIRequest) -> AIResponse: ...

    @property
    def provider_name(self) -> str: ...

    @property
    def endpoint_host(self) -> str: ...
