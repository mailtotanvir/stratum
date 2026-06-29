from app.models.projection import ProjectionSchemaInfo
from app.runtime.projection_contract_validator import (
    ProjectionContractError,
    validate_projection_contract,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.artifact_lineage_projection_builder_service import (
    artifact_lineage_projection_builder,
)
from app.services.decision_projection_builder_service import (
    decision_projection_builder_service,
)
from app.services.decision_lineage_projection_builder_service import (
    decision_lineage_projection_builder,
)
from app.services.decision_effectiveness_projection_builder_service import (
    decision_effectiveness_projection_builder_service,
)
from app.services.evaluation_summary_projection_builder_service import (
    evaluation_summary_projection_builder_service,
)
from app.services.evaluation_coverage_projection_builder_service import (
    evaluation_coverage_projection_builder_service,
)
from app.services.evaluation_drift_projection_builder_service import (
    evaluation_drift_projection_builder_service,
)
from app.services.evaluation_intelligence_overview_projection_builder_service import (
    evaluation_intelligence_overview_projection_builder_service,
)
from app.services.evaluation_trend_projection_v2_builder_service import (
    evaluation_trend_projection_builder_service,
)
from app.services.evaluation_outcome_rollup_projection_builder_service import (
    evaluation_outcome_rollup_projection_builder_service,
)
from app.services.evaluation_lineage_projection_builder_service import (
    evaluation_lineage_projection_builder_service,
)
from app.services.evaluation_registry_projection_builder_service import (
    evaluation_registry_projection_builder_service,
)
from app.services.governance_health_rollup_projection_builder_service import (
    governance_health_rollup_projection_builder_service,
)
from app.services.governance_audit_projection_builder_service import (
    governance_audit_projection_builder,
)
from app.services.policy_evidence_projection_builder_service import (
    policy_evidence_projection_builder_service,
)
from app.services.policy_evaluation_overview_projection_builder_service import (
    policy_evaluation_overview_projection_builder_service,
)
from app.services.policy_projection_builder_service import (
    policy_projection_builder_service,
)
from app.services.recommendation_outcome_projection_builder_service import (
    recommendation_outcome_projection_builder_service,
)
from app.services.session_agent_execution_projection_builder_service import (
    session_agent_execution_projection_builder_service,
)
from app.services.session_decision_projection_builder_service import (
    session_decision_projection_builder_service,
)


class ProjectionTypeAlreadyRegisteredError(ValueError):
    pass


class ProjectionTypeNotFoundError(LookupError):
    pass


class ProjectionRegistry:
    def __init__(self) -> None:
        self._builders: dict[str, BaseProjectionBuilder] = {}
        self._schemas: dict[str, ProjectionSchemaInfo] = {}

    def register(self, builder: BaseProjectionBuilder) -> None:
        schema = validate_projection_contract(builder)
        projection_type = schema.projection_type
        if projection_type in self._builders:
            raise ProjectionTypeAlreadyRegisteredError(
                f"Projection type already registered: {projection_type}"
            )
        self._builders[projection_type] = builder
        self._schemas[projection_type] = schema

    def get(self, projection_type: str) -> BaseProjectionBuilder:
        try:
            return self._builders[projection_type]
        except KeyError as exc:
            raise ProjectionTypeNotFoundError(
                f"Projection type not found: {projection_type}"
            ) from exc

    def list_projection_types(self) -> list[str]:
        return sorted(self._builders)

    def get_schema(self, projection_type: str) -> ProjectionSchemaInfo:
        self.get(projection_type)
        return self._schemas[projection_type].model_copy(deep=True)

    def list_schemas(self) -> list[ProjectionSchemaInfo]:
        return [
            self.get_schema(projection_type)
            for projection_type in self.list_projection_types()
        ]


projection_registry = ProjectionRegistry()
projection_registry.register(artifact_lineage_projection_builder)
projection_registry.register(decision_effectiveness_projection_builder_service)
projection_registry.register(decision_lineage_projection_builder)
projection_registry.register(decision_projection_builder_service)
projection_registry.register(evaluation_coverage_projection_builder_service)
projection_registry.register(evaluation_drift_projection_builder_service)
projection_registry.register(
    evaluation_intelligence_overview_projection_builder_service
)
projection_registry.register(evaluation_outcome_rollup_projection_builder_service)
projection_registry.register(evaluation_lineage_projection_builder_service)
projection_registry.register(evaluation_registry_projection_builder_service)
projection_registry.register(evaluation_summary_projection_builder_service)
projection_registry.register(evaluation_trend_projection_builder_service)
projection_registry.register(governance_audit_projection_builder)
projection_registry.register(governance_health_rollup_projection_builder_service)
projection_registry.register(policy_evidence_projection_builder_service)
projection_registry.register(policy_evaluation_overview_projection_builder_service)
projection_registry.register(policy_projection_builder_service)
projection_registry.register(recommendation_outcome_projection_builder_service)
projection_registry.register(
    session_agent_execution_projection_builder_service
)
projection_registry.register(session_decision_projection_builder_service)
