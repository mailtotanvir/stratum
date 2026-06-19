from fastapi import FastAPI

from app.routes.artifact import router as artifact_router
from app.routes.artifact_lineage import router as artifact_lineage_router
from app.routes.diagnostics import router as diagnostics_router
from app.routes.decision_lineage import router as decision_lineage_router
from app.routes.evaluation_diagnostics import (
    router as evaluation_diagnostics_router,
)
from app.routes.evaluation_outcome_projections import (
    router as evaluation_outcome_projections_router,
)
from app.routes.evaluation_projections import (
    router as evaluation_projections_router,
)
from app.routes.evaluation_trend_projections import (
    router as evaluation_trend_projections_router,
)
from app.routes.evaluation_policy_diagnostics import (
    router as evaluation_policy_diagnostics_router,
)
from app.routes.evaluations import router as evaluations_router
from app.routes.governance import router as governance_router
from app.routes.explainability import router as explainability_router
from app.routes.hitl import router as hitl_router
from app.routes.interrupt import router as interrupt_router
from app.routes.observability import router as observability_router
from app.routes.operational_analytics import (
    router as operational_analytics_router,
)
from app.routes.policies import router as policies_router
from app.routes.policy_diagnostics import router as policy_diagnostics_router
from app.routes.policy_evidence_projections import (
    router as policy_evidence_projections_router,
)
from app.routes.policy_evaluation_overview_projection import (
    router as policy_evaluation_overview_projection_router,
)
from app.routes.policy_projections import router as policy_projections_router
from app.routes.planner import router as planner_router
from app.routes.proposal import router as proposal_router
from app.routes.provider_observability import (
    router as provider_observability_router,
)
from app.routes.query import router as query_router
from app.routes.query_catalog import router as query_catalog_router
from app.routes.query_executor import router as query_executor_router
from app.routes.query_executor_diagnostics import (
    router as query_executor_diagnostics_router,
)
from app.routes.query_health import router as query_health_router
from app.routes.query_manifest import router as query_manifest_router
from app.routes.reconstruct import router as reconstruct_router
from app.routes.reflection import router as reflection_router
from app.routes.runtime import router as runtime_router
from app.routes.runtime_intelligence import (
    router as runtime_intelligence_router,
)
from app.routes.runtime_reconstruction import (
    router as runtime_reconstruction_router,
)
from app.routes.stream import router as stream_router
from app.routes.stop import router as stop_router
from app.routes.task import router as task_router
from app.routes.tool import router as tool_router
from app.routes.tool_invocation import router as tool_invocation_router

app = FastAPI(title="Stratum Backend")
app.include_router(artifact_router)
app.include_router(artifact_lineage_router)
app.include_router(diagnostics_router)
app.include_router(decision_lineage_router)
app.include_router(evaluation_diagnostics_router)
app.include_router(evaluation_outcome_projections_router)
app.include_router(evaluation_projections_router)
app.include_router(evaluation_trend_projections_router)
app.include_router(evaluation_policy_diagnostics_router)
app.include_router(evaluations_router)
app.include_router(explainability_router)
app.include_router(governance_router)
app.include_router(hitl_router)
app.include_router(interrupt_router)
app.include_router(observability_router)
app.include_router(operational_analytics_router)
app.include_router(policies_router)
app.include_router(policy_diagnostics_router)
app.include_router(policy_evidence_projections_router)
app.include_router(policy_evaluation_overview_projection_router)
app.include_router(policy_projections_router)
app.include_router(planner_router)
app.include_router(proposal_router)
app.include_router(provider_observability_router)
app.include_router(query_router)
app.include_router(query_catalog_router)
app.include_router(query_executor_router)
app.include_router(query_executor_diagnostics_router)
app.include_router(query_health_router)
app.include_router(query_manifest_router)
app.include_router(reflection_router)
app.include_router(runtime_router)
app.include_router(runtime_intelligence_router)
app.include_router(runtime_reconstruction_router)
app.include_router(stream_router)
app.include_router(stop_router)
app.include_router(task_router)
app.include_router(tool_router)
app.include_router(tool_invocation_router)
app.include_router(reconstruct_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "stratum-backend"}
