from fastapi import FastAPI

from app.routes.artifact import router as artifact_router
from app.routes.diagnostics import router as diagnostics_router
from app.routes.governance import router as governance_router
from app.routes.hitl import router as hitl_router
from app.routes.interrupt import router as interrupt_router
from app.routes.planner import router as planner_router
from app.routes.proposal import router as proposal_router
from app.routes.query import router as query_router
from app.routes.reconstruct import router as reconstruct_router
from app.routes.reflection import router as reflection_router
from app.routes.runtime import router as runtime_router
from app.routes.stream import router as stream_router
from app.routes.stop import router as stop_router
from app.routes.task import router as task_router
from app.routes.tool import router as tool_router
from app.routes.tool_invocation import router as tool_invocation_router

app = FastAPI(title="Stratum Backend")
app.include_router(artifact_router)
app.include_router(diagnostics_router)
app.include_router(governance_router)
app.include_router(hitl_router)
app.include_router(interrupt_router)
app.include_router(planner_router)
app.include_router(proposal_router)
app.include_router(query_router)
app.include_router(reflection_router)
app.include_router(runtime_router)
app.include_router(stream_router)
app.include_router(stop_router)
app.include_router(task_router)
app.include_router(tool_router)
app.include_router(tool_invocation_router)
app.include_router(reconstruct_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "stratum-backend"}
