from fastapi import FastAPI

app = FastAPI(title="Stratum Backend")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "stratum-backend"}

