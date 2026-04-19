"""
app/main.py
-----------
FastAPI application entry point.

Registers all routers, configures CORS, and sets up startup/shutdown hooks.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import detect, upload
from app.core.config import settings
from app.core.logging import logger, setup_logging


# ────────────────────────────────────────────────────────────────────────────
# Lifespan: startup & shutdown
# ────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan:
      - Startup: configure logging, ensure directories exist, preload model.
      - Shutdown: log graceful stop.
    """
    # ── Startup ───────────────────────────────────────────────────────────
    setup_logging(debug=settings.DEBUG)
    settings.ensure_dirs()
    os.makedirs("logs", exist_ok=True)

    logger.info("=" * 60)
    logger.info("Video Detection Agent starting up")
    logger.info(f"  Model:  {settings.DETECTION_MODEL}")
    logger.info(f"  Device: {settings.DEVICE}")
    logger.info(f"  Upload: {settings.UPLOAD_DIR}")
    logger.info(f"  Results:{settings.RESULTS_DIR}")
    logger.info("=" * 60)

    # Preload the detection model (warm start)
    try:
        from app.services.detector import get_detector
        get_detector()
    except Exception as exc:
        logger.warning(
            f"Model preload failed: {exc}\n"
            "The model will be loaded on the first request."
        )

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("Video Detection Agent shutting down.")


# ────────────────────────────────────────────────────────────────────────────
# Application factory
# ────────────────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Video Object Detection Agent",
        description=(
            "Upload a video and describe what to detect in natural language. "
            "The system uses Grounding DINO + ByteTrack to detect and track "
            "objects frame-by-frame, streaming results in real time."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    # Allow all origins in development; restrict to your domain in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── API Routers ───────────────────────────────────────────────────────
    app.include_router(upload.router, prefix="/api", tags=["Upload"])
    app.include_router(detect.router, prefix="/api", tags=["Detection"])

    # ── Health check ──────────────────────────────────────────────────────
    @app.get("/health", tags=["Health"])
    async def health() -> dict:
        return {
            "status": "ok",
            "model": settings.DETECTION_MODEL,
            "device": settings.DEVICE,
        }

    return app


app = create_app()


# ────────────────────────────────────────────────────────────────────────────
# Entry point (for direct `python -m app.main` or `python main.py`)
# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=1,  # Keep single worker for GPU state sharing
        log_level="debug" if settings.DEBUG else "info",
    )
