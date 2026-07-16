"""
Creator Content Radar — FastAPI application entry point.

Mounts the API routes and serves the static frontend.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Creator Content Radar",
    description="AI-powered YouTube channel analyzer and cross-platform content discovery tool",
    version="0.1.0",
)


@app.get("/health")
async def health_check():
    """Simple liveness probe."""
    return {"status": "ok"}


# Serve the static frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")
