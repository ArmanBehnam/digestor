"""
Digestor Unified - FastAPI Application
Version: 2.0.0

Single entry point serving:
- React frontend (static files)
- REST API endpoints
- WebSocket connections for real-time progress
"""

import os
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from api.endpoints import (
    auth,
    upload,
    process,
    process_aws,
    process_project,
    chat,
    projects,
    results,
    tickets,
    analytics,
    websocket,
    health,
    files,
    admin,
    feedback_survey,
)
from db.session import init_db, close_db

logger = structlog.get_logger()

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("application_starting", version="2.0.0")
    await init_db()
    logger.info("database_initialized")
    yield
    await close_db()
    logger.info("application_shutdown")


app = FastAPI(
    title="Digestor Unified",
    description="Engineering document processing with intelligent PDF.js/AWS fallback",
    version="2.0.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS - same-origin for REST, explicit origins for WebSocket
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8080").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Routers ---
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(process.router, prefix="/api", tags=["process"])
app.include_router(process_aws.router, prefix="/api", tags=["process-aws"])
app.include_router(process_project.router, prefix="/api", tags=["process-project"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(projects.router, prefix="/api", tags=["projects"])
app.include_router(results.router, prefix="/api", tags=["results"])
app.include_router(tickets.router, prefix="/api", tags=["tickets"])
app.include_router(analytics.router, prefix="/api", tags=["analytics"])
app.include_router(files.router, prefix="/api", tags=["files"])
app.include_router(admin.router, prefix="/api", tags=["admin"])
app.include_router(feedback_survey.router, prefix="/api", tags=["feedback"])

# --- WebSocket Router ---
app.include_router(websocket.router, prefix="/ws", tags=["websocket"])


# --- Serve React Frontend (catch-all, must be LAST) ---
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")

if os.path.isdir(STATIC_DIR):
    # Serve static assets (JS, CSS, images)
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(STATIC_DIR, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        """Serve React SPA - all non-API routes return index.html."""
        file_path = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
else:
    @app.get("/")
    async def no_frontend():
        return JSONResponse(
            {"message": "Digestor Unified API v2.0.0 - Frontend not built yet"},
            status_code=200,
        )
