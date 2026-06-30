from __future__ import annotations

from dataclasses import dataclass

from app.models.provider_configuration import ProviderConfiguration
from app.services.provider_configuration_service import (
    ProviderConfigurationService,
    provider_configuration_service,
)


@dataclass(frozen=True)
class ProviderBudgetPolicyResult:
    classification: str
    warnings: list[str]
    metadata: dict[str, object]


class ProviderBudgetPolicyService:
    def __init__(
        self,
        configurations: ProviderConfigurationService | None = None,
    ) -> None:
        self._configurations = (
            configurations or provider_configuration_service
        )

    def resolve(
        self,
        *,
        provider_id: str,
        model: str,
        budget_mode: str | None = None,
        task_type: str | None = None,
        estimated_input_tokens: int | None = None,
        estimated_output_tokens: int | None = None,
    ) -> ProviderBudgetPolicyResult:
        metadata = {
            "provider_id": provider_id,
            "model": model,
        }
        if budget_mode is not None:
            metadata["budget_mode"] = budget_mode
        if task_type is not None:
            metadata["task_type"] = task_type
        if estimated_input_tokens is not None:
            metadata["estimated_input_tokens"] = estimated_input_tokens
        if estimated_output_tokens is not None:
            metadata["estimated_output_tokens"] = estimated_output_tokens

        classification, source = self._classify(
            provider_id=provider_id,
            model=model,
            budget_mode=budget_mode,
        )
        warnings = self._warnings(
            classification=classification,
            budget_mode=budget_mode,
            model=model,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
        )
        return ProviderBudgetPolicyResult(
            classification=classification,
            warnings=warnings,
            metadata={
                **metadata,
                "classification_source": source,
            },
        )

    def _classify(
        self,
        *,
        provider_id: str,
        model: str,
        budget_mode: str | None,
    ) -> tuple[str, str]:
        configuration = (
            self._configurations.get(provider_id)
            if self._configurations.exists(provider_id)
            else None
        )
        config_classification = _metadata_classification(configuration)
        if config_classification is not None:
            return config_classification, "configuration_metadata"

        budget_classification = _budget_mode_classification(budget_mode)
        if budget_classification is not None:
            return budget_classification, "budget_mode"

        model_classification = _model_classification(model)
        if model_classification is not None:
            return model_classification, "model"

        return "unknown", "fallback"

    def _warnings(
        self,
        *,
        classification: str,
        budget_mode: str | None,
        model: str,
        estimated_input_tokens: int | None,
        estimated_output_tokens: int | None,
    ) -> list[str]:
        warnings: list[str] = []
        if (
            budget_mode is not None
            and budget_mode.lower() in {"cheap", "low"}
            and _model_classification(model) == "premium"
        ):
            warnings.append(
                f"Premium model {model} selected under cheap budget_mode."
            )
        if (
            classification == "cheap"
            and estimated_input_tokens is not None
            and estimated_output_tokens is not None
            and estimated_input_tokens + estimated_output_tokens > 20000
        ):
            warnings.append("Estimated token usage is high for a cheap budget.")
        return warnings


def _metadata_classification(
    configuration: ProviderConfiguration | None,
) -> str | None:
    if configuration is None:
        return None
    value = configuration.metadata.get("budget_classification")
    if isinstance(value, str) and value:
        return value
    value = configuration.metadata.get("budget_mode")
    if isinstance(value, str) and value:
        return _budget_mode_classification(value)
    return None


def _budget_mode_classification(budget_mode: str | None) -> str | None:
    if budget_mode is None:
        return None
    normalized = budget_mode.strip().lower()
    if normalized in {"cheap", "low", "economy"}:
        return "cheap"
    if normalized in {"balanced", "standard", "medium"}:
        return "balanced"
    if normalized in {"premium", "high", "expensive"}:
        return "premium"
    return None


def _model_classification(model: str) -> str | None:
    normalized = model.strip().lower()
    if not normalized:
        return None
    premium_markers = ("opus", "pro", "premium", "ultra")
    cheap_markers = ("mini", "small", "haiku", "flash", "lite")
    balanced_markers = ("sonnet", "balanced", "standard", "base")
    if any(marker in normalized for marker in premium_markers):
        return "premium"
    if any(marker in normalized for marker in cheap_markers):
        return "cheap"
    if any(marker in normalized for marker in balanced_markers):
        return "balanced"
    return None


provider_budget_policy_service = ProviderBudgetPolicyService()
