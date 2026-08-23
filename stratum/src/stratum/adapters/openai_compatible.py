"""OpenAI-compatible adapter.

Speaks the /chat/completions dialect shared by OpenAI, Azure OpenAI,
OpenRouter, Groq, Ollama, vLLM, and most local gateways. Uses httpx
directly — no provider SDK leaks into the runtime.
"""

from __future__ import annotations

import time
from urllib.parse import urlsplit

import httpx

from ..ai import AIRequest, AIResponse, AIUsage
from ..errors import ProviderError


class OpenAICompatibleAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        default_model: str | None = None,
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        self._timeout = timeout_seconds
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    @property
    def provider_name(self) -> str:
        return "openai-compatible"

    @property
    def endpoint_host(self) -> str:
        return urlsplit(self._base_url).netloc

    async def generate(self, request: AIRequest) -> AIResponse:
        model = request.model or self._default_model
        if not model:
            raise ProviderError("no model specified and no default model configured")

        payload: dict[str, object] = {
            "model": model,
            "messages": [
                {"role": m.role, "content": m.content} for m in request.messages
            ],
            "temperature": request.temperature,
            "max_completion_tokens": request.max_tokens,
        }
        if request.response_json:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        started = time.monotonic()
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"provider transport failed: {exc}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.status_code >= 400:
            raise ProviderError(
                f"provider returned {response.status_code}: {response.text[:500]}",
                status_code=response.status_code,
            )

        data = response.json()
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"] or ""
            finish_reason = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"malformed provider response: {exc}") from exc

        usage_raw = data.get("usage") or {}
        usage = AIUsage(
            prompt_tokens=int(usage_raw.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage_raw.get("completion_tokens", 0) or 0),
            total_tokens=int(usage_raw.get("total_tokens", 0) or 0),
        )

        return AIResponse(
            request_id=data.get("id"),
            model=data.get("model", model),
            content=content,
            finish_reason=finish_reason,
            usage=usage,
            latency_ms=latency_ms,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
