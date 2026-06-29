from app.models.provider_endpoint_profile import (
    AWS_MANTLE_PROFILE,
    AZURE_OPENAI_PROFILE,
    BUILTIN_OPENAI_COMPATIBLE_PROFILES,
    GROQ_PROFILE,
    OPENAI_PROFILE,
    OPENROUTER_PROFILE,
    SILICONFLOW_PROFILE,
    ProviderEndpointProfile,
)


def test_endpoint_profiles_are_immutable_configuration_only():
    profile = OPENAI_PROFILE

    assert profile.api_style == "openai-compatible"
    assert profile.provider_id == "openai"
    assert profile.base_url == "https://api.openai.com/v1"


def test_builtin_profiles_include_openai_compatible_endpoints():
    provider_ids = [profile.provider_id for profile in BUILTIN_OPENAI_COMPATIBLE_PROFILES]

    assert provider_ids == [
        "openai",
        "azure-openai",
        "aws-mantle",
        "openrouter",
        "siliconflow",
        "groq",
    ]


def test_profiles_are_configuration_not_execution_behavior():
    for profile in BUILTIN_OPENAI_COMPATIBLE_PROFILES:
        dumped = profile.model_dump()

        assert "transport" not in dumped
        assert "adapter" not in dumped
        assert "execute" not in dumped
        assert dumped["api_style"] == "openai-compatible"


def test_profiles_serialize_deterministically():
    first = AWS_MANTLE_PROFILE.model_dump()
    second = AWS_MANTLE_PROFILE.model_dump()

    assert first == second


def test_metadata_and_headers_are_not_shared():
    first = ProviderEndpointProfile(provider_id="a", display_name="A")
    second = ProviderEndpointProfile(provider_id="b", display_name="B")

    assert first.metadata == {}
    assert second.metadata == {}
    assert first.custom_headers == {}
    assert second.custom_headers == {}
    assert first.metadata is not second.metadata
    assert first.custom_headers is not second.custom_headers


def test_specific_profile_shapes():
    assert AZURE_OPENAI_PROFILE.deployment_name is None
    assert OPENROUTER_PROFILE.base_url == "https://openrouter.ai/api/v1"
    assert SILICONFLOW_PROFILE.base_url == "https://api.siliconflow.cn/v1"
    assert GROQ_PROFILE.base_url == "https://api.groq.com/openai/v1"
