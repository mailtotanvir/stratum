import time
from datetime import UTC, datetime

from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionStatus,
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
)
from app.models.provider_live_verification import ProviderLiveVerification
from app.services.provider_configuration_loader_service import (
    ProviderConfigurationLoaderService,
)
from app.services.provider_configuration_service import (
    ProviderConfigurationService,
)
from app.services.provider_configuration_validator_service import (
    ProviderConfigurationError,
    provider_configuration_validator_service,
)
from app.services.provider_execution_service import (
    provider_execution_service_default,
)


class ProviderLiveVerificationService:
    def verify(self) -> ProviderLiveVerification:
        verified_at = datetime.now(UTC)
        config_service = ProviderConfigurationService([])
        configuration = ProviderConfigurationLoaderService().load_from_environment(
            config_service
        )

        if configuration is None:
            return ProviderLiveVerification(
                status="unconfigured",
                reachable=False,
                verified_at=verified_at,
                error_type="ProviderConfigurationError",
                error_message="No live provider environment configuration found.",
            )

        try:
            provider_configuration_validator_service.validate_for_live_execution(
                configuration
            )
        except ProviderConfigurationError as exc:
            return ProviderLiveVerification(
                provider_id=configuration.provider_id,
                model=configuration.default_model,
                status="configuration_error",
                reachable=False,
                verified_at=verified_at,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

        request = ProviderExecutionRequest(
            provider=configuration.provider_id,
            model=configuration.default_model or "",
            mode=ProviderExecutionMode.CHAT,
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content=(
                        "Reply with exactly this sentence: "
                        "Stratum provider verification passed."
                    ),
                )
            ],
            stream_mode=ProviderStreamMode.SSE,
            max_tokens=32,
            metadata={"source": "provider-live-verification"},
        )

        started = time.perf_counter()
        try:
            result = _run_completion(request)
        except Exception as exc:  # noqa: BLE001
            return ProviderLiveVerification(
                provider_id=configuration.provider_id,
                model=configuration.default_model,
                status=_failure_status(exc),
                reachable=False,
                latency_ms=_elapsed_ms(started),
                verified_at=verified_at,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

        latency_ms = _elapsed_ms(started)
        transport = result.metadata.get("transport", {})
        http_status = transport.get("status_code")
        content = result.content or ""

        return ProviderLiveVerification(
            provider_id=configuration.provider_id,
            model=configuration.default_model,
            status=(
                "reachable"
                if result.status == ProviderExecutionStatus.COMPLETED
                else "provider_error"
            ),
            reachable=result.status == ProviderExecutionStatus.COMPLETED,
            latency_ms=latency_ms,
            http_status=http_status if isinstance(http_status, int) else None,
            content_preview=content[:160] if content else None,
            error_type=None if result.error_message is None else "ProviderError",
            error_message=result.error_message,
            verified_at=verified_at,
            metadata={
                "streaming_supported": configuration.supports_streaming,
                "api_style": configuration.api_style,
            },
        )


def _run_completion(request: ProviderExecutionRequest):
    import asyncio

    service = provider_execution_service_default()
    return asyncio.run(service.complete(request))


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _failure_status(exc: Exception) -> str:
    text = str(exc).lower()
    if "401" in text or "unauthorized" in text or "api_key" in text:
        return "authentication_failed"
    if "429" in text or "rate" in text:
        return "rate_limited"
    if "timeout" in text:
        return "timeout"
    if "transport" in text or "connect" in text or "network" in text:
        return "network_error"
    return "provider_error"


provider_live_verification_service = ProviderLiveVerificationService()
