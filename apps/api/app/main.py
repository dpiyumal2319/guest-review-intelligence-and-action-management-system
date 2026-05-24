from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str


app = FastAPI(
    title="Guest Review Intelligence API",
    summary="REST API for the hotel review intelligence prototype.",
    version="0.1.0",
)


@app.get("/health", tags=["system"], response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="api")
