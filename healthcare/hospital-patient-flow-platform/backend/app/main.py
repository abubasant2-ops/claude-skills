"""FastAPI application entry point."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes_admin, routes_ingest, routes_metrics, routes_predictions
from app.core.config import get_settings
from app.core.db import engine, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)
log = logging.getLogger("hpf")

DESCRIPTION = """
Operational intelligence for hospital patient flow.

Excel and CSV extracts are profiled, validated and promoted into a
warehouse, then served as capacity, emergency, journey, quality and
nursing indicators with forecasts on top.

**Reading the numbers**

* Timing indicators report medians, with p90 in each tile's `context`.
* Harm rates are per 1,000 patient days; hospital-acquired only.
* Occupancy is occupancy-weighted, not midnight census.
* Every tile carries `target` and `status`, so a value is never shown
  without the benchmark it is judged against.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log.info("Starting %s in %s mode", settings.app_name, settings.environment)
    # create_all is right for SQLite development and the test suite; a
    # PostgreSQL deployment applies db/schema.sql and Alembic migrations
    # instead, which is why this is a no-op against an existing schema.
    init_db()
    yield
    engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_timing_header(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.1f}"
        if elapsed_ms > 3000:
            log.warning("Slow request %s %s took %.0f ms",
                        request.method, request.url.path, elapsed_ms)
        return response

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        # Domain code raises ValueError for bad input; surfacing it as a 400
        # with the original message beats an opaque 500.
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(routes_ingest.router)
    app.include_router(routes_metrics.router)
    app.include_router(routes_predictions.router)
    app.include_router(routes_admin.router)

    @app.get("/health", tags=["system"], summary="Liveness and database check")
    def health() -> dict:
        from sqlalchemy import text
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            database_ok = True
        except Exception:
            log.exception("Database health check failed")
            database_ok = False
        return {
            "status": "ok" if database_ok else "degraded",
            "database": "up" if database_ok else "down",
            "environment": settings.environment,
            "version": "1.0.0",
        }

    return app


app = create_app()
