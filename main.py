"""
Barrington Home Tracker
-----------------------
FastAPI application that serves both the REST API and the web dashboard.
"""

import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from dotenv import load_dotenv

load_dotenv()

from backend.database import init_db
from backend.routers.listings import router as listings_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db()
    logger.info("Database initialized")
    yield


app = FastAPI(
    title="Barrington Home Tracker",
    description="A home-buying decision support system for Barrington, RI",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the frontend to talk to the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(listings_router)


# Health check
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "app": "Barrington Home Tracker"}


# Serve the frontend dashboard
FRONTEND_DIR = Path(__file__).parent / "frontend"


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the main dashboard page."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(), status_code=200)
    return HTMLResponse(
        content="<h1>Frontend not found</h1><p>Place index.html in /frontend</p>",
        status_code=200,
    )


# Serve static assets from frontend directory
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host=host, port=port, reload=True)
