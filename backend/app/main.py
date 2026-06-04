from fastapi import FastAPI

from app.routes.diagnostics import router as diagnostics_router
from app.routes.hitl import router as hitl_router
from app.routes.proposal import router as proposal_router
from app.routes.reconstruct import router as reconstruct_router
from app.routes.stream import router as stream_router
from app.routes.task import router as task_router

app = FastAPI(title="Stratum Backend")
app.include_router(diagnostics_router)
app.include_router(hitl_router)
app.include_router(proposal_router)
app.include_router(stream_router)
app.include_router(task_router)
app.include_router(reconstruct_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "stratum-backend"}
