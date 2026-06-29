import asyncio
import os

import pytest

from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderExecutionStatus,
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
)
from app.services.provider_execution_service import (
    provider_execution_service_default,
)


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _live_enabled() -> bool:
    return _env("STRATUM_LIVE_PROVIDER_TESTS") == "1"


def _request() -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        provider=_env("STRATUM_PROVIDER_ID"),
        model=_env("STRATUM_PROVIDER_MODEL"),
        mode=ProviderExecutionMode.CHAT,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content=(
                    "Reply with exactly this sentence: "
                    "Stratum live provider test passed."
                ),
            )
        ],
        stream_mode=ProviderStreamMode.SSE,
    )


@pytest.mark.skipif(
    not _live_enabled(),
    reason="Set STRATUM_LIVE_PROVIDER_TESTS=1 to run live provider smoke tests.",
)
def test_live_provider_completion_over_real_http() -> None:
    required = [
        "STRATUM_PROVIDER_ID",
        "STRATUM_PROVIDER_BASE_URL",
        "STRATUM_PROVIDER_API_KEY",
        "STRATUM_PROVIDER_MODEL",
    ]
    missing = [name for name in required if not _env(name)]
    if missing:
        pytest.fail(f"Missing live provider env vars: {missing}")

    service = provider_execution_service_default()

    result = asyncio.run(service.complete(_request()))

    assert result.status == ProviderExecutionStatus.COMPLETED
    assert result.provider == _env("STRATUM_PROVIDER_ID")
    assert result.model == _env("STRATUM_PROVIDER_MODEL")
    assert result.content
    assert "transport" in result.metadata
    assert result.metadata["transport"]["status_code"] == 200


@pytest.mark.skipif(
    not _live_enabled(),
    reason="Set STRATUM_LIVE_PROVIDER_TESTS=1 to run live provider smoke tests.",
)
def test_live_provider_streaming_over_real_http() -> None:
    required = [
        "STRATUM_PROVIDER_ID",
        "STRATUM_PROVIDER_BASE_URL",
        "STRATUM_PROVIDER_API_KEY",
        "STRATUM_PROVIDER_MODEL",
    ]
    missing = [name for name in required if not _env(name)]
    if missing:
        pytest.fail(f"Missing live provider env vars: {missing}")

    service = provider_execution_service_default()

    async def collect() -> list[str]:
        contents: list[str] = []
        async for event in service.stream(_request()):
            if event.content:
                contents.append(event.content)
        return contents

    chunks = asyncio.run(collect())

    assert "".join(chunks).strip()
