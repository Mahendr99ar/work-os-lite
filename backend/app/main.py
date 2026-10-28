"""App entry point: `uvicorn app.main:app --reload`"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine, init_db
from app.routers import audit, auth, documents, planner, projects, tasks, team

log = logging.getLogger("workos")


DEFAULT_JWT_SECRET = "change-me-in-production"


def check_settings() -> None:
    """Refuse to start a real deployment with settings that make it unsafe."""
    real_database = not settings.database_url.startswith("sqlite")
    if settings.jwt_secret == DEFAULT_JWT_SECRET:
        if real_database:
            # Anyone who reads this repo could sign tokens for any team.
            raise RuntimeError("JWT_SECRET is the default value. Set a long random secret before starting.")
        log.warning("JWT_SECRET is the default value. Fine for local SQLite, never for a deployment.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    check_settings()
    init_db()
    yield


app = FastAPI(title="Work OS Lite API", version="1.1.0", lifespan=lifespan)


@app.middleware("http")
async def catch_unexpected_errors(request: Request, call_next):
    """Turn crashes into a JSON 500.

    This middleware is added before CORS, so it sits inside it. A crash caught
    here still gets CORS headers, and the browser shows the real error instead
    of a confusing "blocked by CORS policy" message.
    """
    try:
        return await call_next(request)
    except Exception:
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Something went wrong on the server. Check the server logs."}, status_code=500)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,  # e.g. https://.*\.vercel\.app for preview deploys
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (auth.router, team.router, projects.router, tasks.router, documents.router, planner.router, audit.router):
    app.include_router(router)


@app.get("/ping", tags=["health"])
def ping() -> dict:
    """Liveness check that does not touch the database.

    Render's health check and keep-awake pingers use this one. If they hit
    /health instead, Neon's free database would never get to sleep and the
    monthly compute hours would run out.
    """
    return {"status": "ok"}


@app.get("/health", tags=["health"])
def health() -> JSONResponse:
    """Full check, including the database. Open it by hand after a deploy."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "error", "database": "unreachable"}, status_code=503)
    return JSONResponse({"status": "ok", "database": "ok"})


@app.get("/meta", tags=["health"])
def meta() -> dict:
    """What the frontend needs to know about this server. No secrets."""
    return {
        "demo_mode": settings.demo_mode,
        "llm_configured": settings.llm_configured,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "embedding_provider": settings.embedding_provider,
    }
