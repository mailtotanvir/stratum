"""Scripted adapter — deterministic canned responses.

FOR FAST TESTS AND OFFLINE DEVELOPMENT ONLY. A scripted adapter can never
constitute acceptance evidence; the primary acceptance path requires a real
configured provider (see tests/acceptance).
"""

from __future__ import annotations

from collections.abc import Callable

from ..ai import AIRequest, AIResponse, AIUsage
from ..errors import ProviderError


class ScriptedAdapter:
    def __init__(
        self,
        responses: list[AIResponse] | None = None,
        responder: Callable[[AIRequest], AIResponse] | None = None,
    ) -> None:
        if not responses and not responder:
            raise ValueError("ScriptedAdapter needs responses or a responder")
        self._responses = list(responses or [])
        self._responder = responder
        self.requests: list[AIRequest] = []

    @property
    def provider_name(self) -> str:
        return "scripted"

    @property
    def endpoint_host(self) -> str:
        return "scripted.local"

    async def generate(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        if self._responder is not None:
            return self._responder(request)
        if not self._responses:
            raise ProviderError("scripted adapter exhausted")
        return self._responses.pop(0)


def scripted_json_response(content: str, *, model: str = "scripted-model") -> AIResponse:
    return AIResponse(
        request_id="chatcmpl-scripted",
        model=model,
        content=content,
        finish_reason="stop",
        usage=AIUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        latency_ms=1,
    )
