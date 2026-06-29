import asyncio
import os
import sys

from app.models.provider_execution import (
    ProviderExecutionMode,
    ProviderExecutionRequest,
    ProviderMessage,
    ProviderMessageRole,
    ProviderStreamMode,
)
from app.services.live_provider_execution_service import (
    live_provider_execution_service_factory,
)


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _request() -> ProviderExecutionRequest:
    provider_id = _required("STRATUM_PROVIDER_ID")
    model = _required("STRATUM_PROVIDER_MODEL")
    prompt = os.environ.get(
        "STRATUM_PROVIDER_PROMPT",
        "Reply with exactly: Stratum live provider smoke test passed.",
    )

    return ProviderExecutionRequest(
        provider=provider_id,
        model=model,
        mode=ProviderExecutionMode.CHAT,
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content=prompt,
            )
        ],
        stream_mode=ProviderStreamMode.SSE,
    )


async def _complete() -> int:
    service = live_provider_execution_service_factory.create_from_environment()
    result = await service.complete(_request())

    print("=== Live Provider Completion ===")
    print(f"status: {result.status}")
    print(f"provider: {result.provider}")
    print(f"model: {result.model}")
    print("content:")
    print(result.content or "")
    if result.usage is not None:
        print("usage:")
        print(result.usage.model_dump(mode="json"))

    return 0


async def _stream() -> int:
    service = live_provider_execution_service_factory.create_from_environment()

    print("=== Live Provider Stream ===")
    async for event in service.stream(_request()):
        if event.content:
            print(event.content, end="", flush=True)
        if event.event_type == "completed":
            print()

    return 0


async def main() -> int:
    mode = os.environ.get("STRATUM_PROVIDER_SMOKE_MODE", "complete").strip()
    if mode == "complete":
        return await _complete()
    if mode == "stream":
        return await _stream()

    raise RuntimeError(
        "Unsupported STRATUM_PROVIDER_SMOKE_MODE. "
        "Use 'complete' or 'stream'."
    )


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(f"live provider smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
