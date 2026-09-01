import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core.config import settings
from app.routers import auth, cost, documents, price_book, projects, takeoff

logging.basicConfig(level=getattr(logging, settings.app_log_level.upper(), logging.INFO))

app = FastAPI(
    title="ArcVision AI",
    version=__version__,
    description=(
        "منصة ذكاء اصطناعي لتحليل المشاريع الإنشائية — MVP\n\n"
        "Multi-tenant (RLS) · RBAC · async pipeline (Celery) · provenance + confidence."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": __version__, "env": settings.app_env}


app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(takeoff.router)
app.include_router(price_book.router)
app.include_router(cost.router)
