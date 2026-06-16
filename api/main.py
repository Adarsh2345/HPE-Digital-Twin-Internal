"""
api/main.py
FastAPI application entry point.
Starts the orchestrator bootstrap and 12s telemetry loop on startup.
"""
import asyncio
import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import API_HOST, API_PORT, DEBUG
from config.constants import APP_NAME
from api.routes import topology, telemetry, simulation, chaos, reports, analytics

from core.orchestrator import orchestrator

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {APP_NAME}")
    orchestrator.bootstrap()

    loop_task = asyncio.create_task(orchestrator.start_telemetry_loop())
    logger.info("Background telemetry loop launched ✓")

    yield

    loop_task.cancel()
    logger.info("Telemetry loop stopped")


app = FastAPI(
    title=APP_NAME,
    version="1.0.0",
    description=(
        "Config-file-driven Digital Twin Orchestrator for HPE private cloud infrastructure. "
        "Provides live topology graphs, real-time Prometheus-style telemetry, "
        "what-if simulation with RCU isolation, and 4-tier constraint validation."
    ),
    lifespan=lifespan,
    servers=[{"url": "http://localhost:5000", "description": "Local dev server"}],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(topology.router)
app.include_router(telemetry.router)
app.include_router(simulation.router)
app.include_router(chaos.router)
app.include_router(reports.router)
app.include_router(analytics.router)

@app.get("/", tags=["Root"])
def root():
    return {
        "app": APP_NAME,
        "version": "1.0.0",
        "docs": "/docs",
        "status": "/api/v1/telemetry/status",
        "topology": "/api/v1/topology",
        "simulate": "/api/v1/simulate",
    }


@app.get("/health", tags=["Root"])
def health():
    return {"status": "ok", "app": APP_NAME}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=DEBUG)
