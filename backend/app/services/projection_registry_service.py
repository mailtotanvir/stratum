from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from app.models.projection import (
    ProjectionCapability,
    ProjectionContract,
    ProjectionRegistryCatalog,
    ProjectionRegistryDetail,
    ProjectionRegistryEntry,
)
from app.models.runtime_event import EventType, Severity
from app.services.event_service import EventService, event_service


class ProjectionContractValidationError(ValueError):
    pass


class ProjectionRegistrationError(ValueError):
    pass


class ProjectionContractNotFoundError(LookupError):
    pass


class ProjectionRegistryService:
    def __init__(
        self,
        events: EventService | None = None,
        initial_contracts: Iterable[ProjectionContract | dict[str, Any]]
        | None = None,
        emit_initial_diagnostics: bool = False,
    ) -> None:
        self._events = events or event_service
        self._contracts: dict[str, ProjectionContract] = {}
        self._validation_failures_total = 0
        self._queries_total = 0
        for contract in initial_contracts or []:
            self.register(
                contract,
                emit_diagnostics=emit_initial_diagnostics,
            )

    def register(
        self,
        contract: ProjectionContract | dict[str, Any],
        *,
        emit_diagnostics: bool = True,
    ) -> ProjectionRegistryEntry:
        try:
            parsed = self.validate_contract(
                contract,
                emit_diagnostics=emit_diagnostics,
            )
            if parsed.projection_name in self._contracts:
                raise ProjectionRegistrationError(
                    "Projection already registered: "
                    f"{parsed.projection_name}"
                )
            self._contracts[parsed.projection_name] = parsed
        except Exception as exc:
            if isinstance(
                exc,
                (
                    ProjectionRegistrationError,
                    ProjectionContractValidationError,
                    ValidationError,
                ),
            ):
                self._emit(
                    EventType.PROJECTION_REGISTRATION_FAILED,
                    "Projection registration failed",
                    Severity.ERROR,
                    projection_name=_projection_name(contract),
                    error_type=type(exc).__name__,
                )
            raise

        entry = self._entry(parsed)
        if emit_diagnostics:
            self._emit(
                EventType.PROJECTION_REGISTERED,
                "Projection registered",
                projection_name=parsed.projection_name,
                projection_version=parsed.projection_version,
                projection_category=parsed.projection_category,
            )
        return entry

    def validate_contract(
        self,
        contract: ProjectionContract | dict[str, Any],
        *,
        emit_diagnostics: bool = True,
    ) -> ProjectionContract:
        try:
            parsed = (
                contract
                if isinstance(contract, ProjectionContract)
                else ProjectionContract.model_validate(contract)
            )
            self._validate_capabilities(parsed)
        except Exception as exc:
            self._validation_failures_total += 1
            if emit_diagnostics:
                self._emit(
                    EventType.PROJECTION_CONTRACT_INVALID,
                    "Projection contract invalid",
                    Severity.ERROR,
                    projection_name=_projection_name(contract),
                    error_type=type(exc).__name__,
                )
            if isinstance(exc, ValidationError):
                raise
            raise ProjectionContractValidationError(str(exc)) from exc

        if emit_diagnostics:
            self._emit(
                EventType.PROJECTION_CONTRACT_VALIDATED,
                "Projection contract validated",
                projection_name=parsed.projection_name,
                projection_version=parsed.projection_version,
                projection_category=parsed.projection_category,
            )
        return parsed

    def list_registry(self) -> ProjectionRegistryCatalog:
        self._queries_total += 1
        entries = [
            self._entry(self._contracts[name])
            for name in sorted(self._contracts)
        ]
        return ProjectionRegistryCatalog(
            projections=entries,
            registered_projections_total=len(entries),
            observability_metrics=self.observability_metrics(),
        )

    def get(self, projection_name: str) -> ProjectionRegistryDetail:
        self._queries_total += 1
        try:
            contract = self._contracts[projection_name]
        except KeyError as exc:
            raise ProjectionContractNotFoundError(
                f"Projection contract not found: {projection_name}"
            ) from exc
        entry = self._entry(contract)
        return ProjectionRegistryDetail(
            **entry.model_dump(),
            version_information={
                "projection_name": contract.projection_name,
                "registered_version": contract.projection_version,
                "version_rule": "one_active_version_per_projection_name",
            },
            observability_metrics=self.observability_metrics(),
        )

    def capabilities(self, projection_name: str) -> ProjectionCapability:
        return self.get(projection_name).capabilities

    def observability_metrics(self) -> dict[str, int]:
        return {
            "registered_projections_total": len(self._contracts),
            "projection_contract_validation_failures_total": (
                self._validation_failures_total
            ),
            "projection_registry_queries_total": self._queries_total,
        }

    @staticmethod
    def _validate_capabilities(contract: ProjectionContract) -> None:
        if (
            contract.supports_drift_detection
            and not contract.supports_replay
        ):
            raise ValueError(
                "Drift detection requires replay support"
            )
        if contract.supports_analytics and not contract.supports_reconstruction:
            raise ValueError(
                "Analytics support requires reconstruction support"
            )
        if (
            contract.supports_explainability
            and not contract.supports_reconstruction
        ):
            raise ValueError(
                "Explainability support requires reconstruction support"
            )

    @staticmethod
    def _entry(contract: ProjectionContract) -> ProjectionRegistryEntry:
        return ProjectionRegistryEntry(
            projection_name=contract.projection_name,
            projection_version=contract.projection_version,
            projection_category=contract.projection_category,
            contract=contract.model_copy(deep=True),
            capabilities=ProjectionCapability(
                replayable=contract.supports_replay,
                drift_checkable=contract.supports_drift_detection,
                reconstructable=contract.supports_reconstruction,
                analyzable=contract.supports_analytics,
                explainable=contract.supports_explainability,
            ),
        )

    def _emit(
        self,
        event_type: EventType,
        message: str,
        severity: Severity = Severity.INFO,
        **metadata: Any,
    ) -> None:
        self._events.emit_event_sync(
            event_type=event_type,
            severity=severity,
            message=message,
            metadata={
                key: value
                for key, value in metadata.items()
                if value is not None
            },
        )


def _projection_name(contract: ProjectionContract | dict[str, Any]) -> str | None:
    if isinstance(contract, ProjectionContract):
        return contract.projection_name
    value = contract.get("projection_name")
    return value if isinstance(value, str) else None


def default_projection_contracts() -> list[ProjectionContract]:
    return [
        ProjectionContract(
            projection_name="artifact_lineage_projection",
            projection_version=1,
            projection_description="Reconstructs artifact provenance and links.",
            projection_owner="runtime_observability",
            projection_category="lineage",
            supports_replay=True,
            supports_drift_detection=True,
            supports_reconstruction=True,
            supports_analytics=True,
            supports_explainability=True,
        ),
        ProjectionContract(
            projection_name="decision_lineage_projection",
            projection_version=1,
            projection_description="Reconstructs decision ancestry and evidence links.",
            projection_owner="runtime_observability",
            projection_category="lineage",
            supports_replay=True,
            supports_drift_detection=True,
            supports_reconstruction=True,
            supports_analytics=True,
            supports_explainability=True,
        ),
        ProjectionContract(
            projection_name="decision_projection",
            projection_version=1,
            projection_description="Summarizes runtime decisions for a session.",
            projection_owner="runtime",
            projection_category="decision",
            supports_replay=True,
            supports_drift_detection=True,
            supports_reconstruction=True,
            supports_analytics=True,
            supports_explainability=True,
        ),
        ProjectionContract(
            projection_name="evaluation_summary",
            projection_version=1,
            projection_description="Summarizes persisted evaluations and result dimensions.",
            projection_owner="runtime",
            projection_category="evaluation",
            supports_replay=True,
            supports_drift_detection=True,
            supports_reconstruction=True,
            supports_analytics=True,
            supports_explainability=True,
        ),
        ProjectionContract(
            projection_name="evaluation_outcome_rollup",
            projection_version=1,
            projection_description="Aggregates evaluation outcomes by normalized evaluated target.",
            projection_owner="runtime",
            projection_category="evaluation",
            supports_replay=True,
            supports_drift_detection=True,
            supports_reconstruction=True,
            supports_analytics=True,
            supports_explainability=True,
        ),
        ProjectionContract(
            projection_name="evaluation_trend",
            projection_version=1,
            projection_description="Buckets evaluation activity and result scores over time.",
            projection_owner="runtime",
            projection_category="evaluation",
            supports_replay=True,
            supports_drift_detection=True,
            supports_reconstruction=True,
            supports_analytics=True,
            supports_explainability=True,
        ),
        ProjectionContract(
            projection_name="explainability",
            projection_version=1,
            projection_description="Derived explanations for decisions, artifacts, and sessions.",
            projection_owner="runtime_observability",
            projection_category="explainability",
            supports_replay=False,
            supports_drift_detection=False,
            supports_reconstruction=True,
            supports_analytics=False,
            supports_explainability=True,
        ),
        ProjectionContract(
            projection_name="governance_audit_projection",
            projection_version=1,
            projection_description="Reconstructs governance decisions and policy actions.",
            projection_owner="governance",
            projection_category="governance",
            supports_replay=True,
            supports_drift_detection=True,
            supports_reconstruction=True,
            supports_analytics=True,
            supports_explainability=True,
        ),
        ProjectionContract(
            projection_name="operational_analytics",
            projection_version=1,
            projection_description="Aggregates operational metrics from derived runtime evidence.",
            projection_owner="runtime_observability",
            projection_category="analytics",
            supports_replay=False,
            supports_drift_detection=False,
            supports_reconstruction=True,
            supports_analytics=True,
            supports_explainability=False,
        ),
        ProjectionContract(
            projection_name="policy_evidence",
            projection_version=1,
            projection_description="Summarizes policy decisions and violations linked to evaluation evidence.",
            projection_owner="runtime",
            projection_category="policy",
            supports_replay=True,
            supports_drift_detection=True,
            supports_reconstruction=True,
            supports_analytics=True,
            supports_explainability=True,
        ),
        ProjectionContract(
            projection_name="policy_evaluation_overview",
            projection_version=1,
            projection_description="Summarizes policy and evaluation linkage across runtime state.",
            projection_owner="runtime",
            projection_category="policy",
            supports_replay=True,
            supports_drift_detection=True,
            supports_reconstruction=True,
            supports_analytics=True,
            supports_explainability=True,
        ),
        ProjectionContract(
            projection_name="policy_summary",
            projection_version=1,
            projection_description="Summarizes policy state, versions, decisions, and violations.",
            projection_owner="runtime",
            projection_category="policy",
            supports_replay=True,
            supports_drift_detection=True,
            supports_reconstruction=True,
            supports_analytics=True,
            supports_explainability=True,
        ),
        ProjectionContract(
            projection_name="runtime_intelligence",
            projection_version=1,
            projection_description="Classifies runtime risks and high-signal activity.",
            projection_owner="runtime_observability",
            projection_category="intelligence",
            supports_replay=False,
            supports_drift_detection=False,
            supports_reconstruction=True,
            supports_analytics=True,
            supports_explainability=False,
        ),
        ProjectionContract(
            projection_name="runtime_reconstruction_view",
            projection_version=1,
            projection_description="Composes session reconstruction views from event-backed evidence.",
            projection_owner="runtime_observability",
            projection_category="reconstruction",
            supports_replay=False,
            supports_drift_detection=False,
            supports_reconstruction=True,
            supports_analytics=True,
            supports_explainability=True,
        ),
        ProjectionContract(
            projection_name="session_decision_projection",
            projection_version=1,
            projection_description="Aggregates decision projection records for a session.",
            projection_owner="runtime",
            projection_category="decision",
            supports_replay=True,
            supports_drift_detection=True,
            supports_reconstruction=True,
            supports_analytics=True,
            supports_explainability=True,
        ),
    ]


projection_registry_service = ProjectionRegistryService(
    initial_contracts=default_projection_contracts(),
)
