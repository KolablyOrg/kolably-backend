"""
Kolably Backend — FastAPI Application Entry Point.

Run with:
    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging_config import configure_logging
from app.core.scheduler import start_scheduler, stop_scheduler

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Kolably API",
    description="Local Business × Creator Collaboration Marketplace",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

register_exception_handlers(app)

# ── CORS ──────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")


# ── Health Check ──────────────────────────────────────
@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}
