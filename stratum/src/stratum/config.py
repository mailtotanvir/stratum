"""Provider configuration resolution.

Credentials are resolved as coherent (base_url, api_key) PAIRS, never mixed.
Precedence:
1. Explicit STRATUM_PROVIDER_BASE_URL + STRATUM_PROVIDER_API_KEY
2. Groq (GROQ_API_KEY) at its OpenAI-compatible endpoint
3. OpenAI / Azure OpenAI pair (OPENAI_API_BASE + OPENAI_API_KEY)
"""

from __future__ import annotations

import os
from dataclasses import dataclass

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    api_key: str
    model: str


def resolve_provider(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> ProviderConfig | None:
    base_url = base_url or os.environ.get("STRATUM_PROVIDER_BASE_URL")
    api_key = api_key or os.environ.get("STRATUM_PROVIDER_API_KEY")

    if not (base_url and api_key):
        groq_key = os.environ.get("GROQ_API_KEY")
        if groq_key and not base_url:
            base_url = GROQ_BASE_URL
            api_key = api_key or groq_key
        else:
            oai_base = os.environ.get("OPENAI_API_BASE") or (
                base_url if base_url else OPENAI_BASE_URL
            )
            oai_key = os.environ.get("OPENAI_API_KEY")
            if base_url and oai_key:
                api_key = api_key or oai_key
            elif oai_base and oai_key:
                base_url = base_url or oai_base
                api_key = oai_key

    if not (base_url and api_key):
        return None

    resolved_model = (
        model
        or os.environ.get("STRATUM_MODEL")
        or (DEFAULT_GROQ_MODEL if base_url == GROQ_BASE_URL else None)
    )
    return ProviderConfig(base_url=base_url, api_key=api_key, model=resolved_model)
