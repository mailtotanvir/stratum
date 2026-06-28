from collections.abc import Callable
from time import monotonic
from typing import Any

import httpx
from pydantic import ValidationError

from app.models.provider_execution import (
    ProviderExecutionRequest,
    ProviderExecutionResult,
    ProviderExecutionStatus,
    ProviderUsage,
)
from app.providers.base_provider import BaseProvider


OPENAI_COMPATIBLE_PROVIDER_NAME = "openai-compatible"
OPENAI_COMPATIBLE_BASE_URL = "https://api.openai.com/v1"


class MalformedProviderResponseError(ValueError):
    pass


class OpenAICompatibleProvider(BaseProvider):
    def __init__(
        self,
        provider_name: str,
        base_url: str,
        api_key: str,
        default_headers: dict[str, str] | None = None,
        client: httpx.Client | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not provider_name.strip():
            raise ValueError("provider_name must not be empty")
        if not base_url.strip():
            raise ValueError("base_url must not be empty")
        self._provider_name = provider_name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_headers = dict(default_headers or {})
        self._client = client
        self._clock = clock or monotonic

    def provider_name(self) -> str:
        return self._provider_name

    def supported_models(self) -> list[str]:
        return []

    def supports_streaming(self, model: str) -> bool:
        del model
        return False

    def execute(
        self,
        request: ProviderExecutionRequest,
    ) -> ProviderExecutionResult:
        endpoint = f"{self._base_url}/chat/completions"
        started_at = self._clock()
        try:
            response = self._post(
                endpoint,
                json=_request_payload(request),
                headers=self._headers(),
            )
        except httpx.TimeoutException:
            return self._failed_result(
                request,
                "Provider request timed out.",
                started_at,
                error_type="timeout",
            )
        except httpx.HTTPError:
            return self._failed_result(
                request,
                "Provider HTTP request failed.",
                started_at,
                error_type="http_error",
            )

        if response.is_error:
            return self._failed_result(
                request,
                f"Provider returned HTTP {response.status_code}.",
                started_at,
                error_type="http_status_error",
                status_code=response.status_code,
            )

        try:
            payload = response.json()
        except ValueError:
            return self._failed_result(
                request,
                "Provider returned invalid JSON.",
                started_at,
                error_type="invalid_json",
                status_code=response.status_code,
            )

        if not isinstance(payload, dict):
            return self._failed_result(
                request,
                "Provider returned a malformed response.",
                started_at,
                error_type="malformed_response",
                status_code=response.status_code,
            )

        try:
            content = _response_content(payload)
        except MalformedProviderResponseError:
            return self._failed_result(
                request,
                "Provider returned a malformed response.",
                started_at,
                error_type="malformed_response",
                status_code=response.status_code,
                raw_response=payload,
            )
        if content is None:
            return self._failed_result(
                request,
                "Provider response is missing assistant content.",
                started_at,
                error_type="missing_content",
                status_code=response.status_code,
                raw_response=payload,
            )

        try:
            usage = _response_usage(payload)
        except (TypeError, ValueError, ValidationError):
            return self._failed_result(
                request,
                "Provider returned malformed usage data.",
                started_at,
                error_type="malformed_usage",
                status_code=response.status_code,
                raw_response=payload,
            )

        return ProviderExecutionResult(
            status=ProviderExecutionStatus.COMPLETED,
            provider=request.provider,
            model=request.model,
            content=content,
            raw_response=payload,
            usage=usage,
            latency_ms=_latency_ms(started_at, self._clock()),
            metadata={
                "adapter": self.provider_name(),
                "endpoint": endpoint,
                "status_code": response.status_code,
            },
        )

    def _post(
        self,
        endpoint: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        if self._client is not None:
            return self._client.post(
                endpoint,
                json=json,
                headers=headers,
            )
        with httpx.Client() as client:
            return client.post(
                endpoint,
                json=json,
                headers=headers,
            )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **self._default_headers,
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _failed_result(
        self,
        request: ProviderExecutionRequest,
        error_message: str,
        started_at: float,
        *,
        error_type: str,
        status_code: int | None = None,
        raw_response: dict[str, Any] | None = None,
    ) -> ProviderExecutionResult:
        metadata: dict[str, Any] = {
            "adapter": self.provider_name(),
            "endpoint": f"{self._base_url}/chat/completions",
            "error_type": error_type,
        }
        if status_code is not None:
            metadata["status_code"] = status_code
        return ProviderExecutionResult(
            status=ProviderExecutionStatus.FAILED,
            provider=request.provider,
            model=request.model,
            raw_response=raw_response,
            error_message=error_message,
            latency_ms=_latency_ms(started_at, self._clock()),
            metadata=metadata,
        )


def _request_payload(
    request: ProviderExecutionRequest,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": request.model,
        "messages": [
            {
                key: value
                for key, value in {
                    "role": message.role.value,
                    "content": message.content,
                    "name": message.name,
                    "tool_call_id": message.tool_call_id,
                }.items()
                if value is not None
            }
            for message in request.messages
        ],
        "stream": False,
    }
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    return payload


def _response_content(payload: dict[str, Any]) -> str | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise MalformedProviderResponseError
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise MalformedProviderResponseError
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise MalformedProviderResponseError
    content = message.get("content")
    if content is None or content == "":
        return None
    if not isinstance(content, str):
        raise MalformedProviderResponseError
    return content


def _response_usage(payload: dict[str, Any]) -> ProviderUsage | None:
    raw_usage = payload.get("usage")
    if raw_usage is None:
        return None
    if not isinstance(raw_usage, dict):
        raise TypeError("usage must be an object")
    return ProviderUsage(
        input_tokens=_optional_int(raw_usage.get("prompt_tokens")),
        output_tokens=_optional_int(raw_usage.get("completion_tokens")),
        total_tokens=_optional_int(raw_usage.get("total_tokens")),
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("token counts must be integers")
    return value


def _latency_ms(started_at: float, completed_at: float) -> int:
    return max(0, round((completed_at - started_at) * 1000))
