from fastapi import FastAPI

from app.routes.hitl import router as hitl_router
from app.routes.stream import router as stream_router

app = FastAPI(title="Stratum Backend")
app.include_router(hitl_router)
app.include_router(stream_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "stratum-backend"}
