"""Error types for the Stratum runtime."""

from __future__ import annotations


class StratumError(Exception):
    """Base class for all Stratum runtime errors."""


class RepositoryError(StratumError):
    """The target repository is invalid or unusable."""


class ProviderError(StratumError):
    """An AI provider interaction failed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PlanValidationError(StratumError):
    """The AI response could not be parsed into a valid plan."""


class ApprovalRequiredError(StratumError):
    """Execution was attempted without an approved plan."""


class InvalidTransitionError(StratumError):
    """A lifecycle transition violated the execution contract."""


class ToolError(StratumError):
    """A tool invocation failed."""
