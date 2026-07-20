"""
Creator Content Radar — FastAPI application entry point.

Integrates channel analysis, competitor discovery, topic search,
JWT authentication, Stripe billing, rate limiting, and monitoring.
"""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.channel_analyzer import analyze_channel
from app.competitor_finder import find_competitors
from app.db import get_cached_channel_profile, get_session, init_db
from app.models import ChannelProfile, CompetitorChannel, ContentResult, TopicInsight
from app.topic_search import search_topic_with_insights

# Auth
from app.auth import get_current_user
from app.db import User

# Routers
from app.routers.auth import router as auth_router
from app.routers.billing import router as billing_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)


# ---------------------------------------------------------------------------
# URL Validation
# ---------------------------------------------------------------------------

_VALID_YOUTUBE_RE = re.compile(
    r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+|@[\w.-]+|UC[\w-]{22}$",
    re.IGNORECASE,
)


def _validate_youtube_url(url: str) -> None:
    """Raise ValueError if *url* is not a valid YouTube channel URL or ID."""
    if not url or not url.strip():
        raise ValueError("Channel URL is required")
    if not _VALID_YOUTUBE_RE.match(url.strip()):
        raise ValueError(
            "Invalid YouTube URL. Use formats like: "
            "https://www.youtube.com/@handle, "
            "https://www.youtube.com/channel/UC..., or "
            "https://www.youtube.com/c/Name"
        )


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class AnalyzeChannelRequest(BaseModel):
    """Request body for POST /analyze-channel."""

    channel_url: str = Field(..., description="YouTube channel URL or ID")


class FindCompetitorsRequest(BaseModel):
    """Request body for POST /find-competitors."""

    channel_id: str = Field(..., description="YouTube channel ID")


class SearchTopicRequest(BaseModel):
    """Request body for POST /search-topic."""

    channel_id: str = Field(..., description="YouTube channel ID")
    topic: str = Field(..., description="Topic to search for")
    competitor_channel_ids: list[str] = Field(
        default_factory=list,
        description="List of competitor channel IDs to include in search",
    )


class SearchTopicResponse(BaseModel):
    """Response body for POST /search-topic."""

    results: list[ContentResult]
    insight: TopicInsight


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup."""
    init_db()
    yield


app = FastAPI(
    title="Creator Content Radar",
    description="AI-powered YouTube channel analyzer and cross-platform content discovery tool",
    version="0.2.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth_router)
app.include_router(billing_router)

# Prometheus monitoring (optional — fails gracefully if not installed)
try:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
except ImportError:
    logger.info("prometheus-fastapi-instrumentator not installed — /metrics disabled")


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@app.post("/analyze-channel", response_model=ChannelProfile)
@limiter.limit("5/minute")
async def analyze_channel_endpoint(
    request: Request,
    body: AnalyzeChannelRequest,
) -> ChannelProfile:
    """Analyze a YouTube channel and return its niche profile.

    Accepts a YouTube channel URL or ID, fetches channel data via the YouTube Data API,
    and uses AI to determine niche, topics, content style, and target audience.
    """
    try:
        _validate_youtube_url(body.channel_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    logger.info("POST /analyze-channel - channel_url=%s", body.channel_url)

    try:
        profile = analyze_channel(body.channel_url)
        logger.info(
            "POST /analyze-channel SUCCESS - channel_id=%s, title=%s",
            profile.channel_id,
            profile.title,
        )
        return profile
    except ValueError as exc:
        logger.error("POST /analyze-channel BAD_INPUT - %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("POST /analyze-channel ERROR - %s", exc)
        if "quota" in str(exc).lower() or "403" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="YouTube API quota exhausted. Try again in a few hours.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream API failure: {str(exc)}",
        ) from exc


@app.post("/find-competitors", response_model=list[CompetitorChannel])
@limiter.limit("10/minute")
async def find_competitors_endpoint(
    request: Request,
    body: FindCompetitorsRequest,
) -> list[CompetitorChannel]:
    """Find competitor channels for a given YouTube channel."""
    logger.info("POST /find-competitors - channel_id=%s", body.channel_id)

    try:
        profile = get_cached_channel_profile(body.channel_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Channel profile not found for channel_id={body.channel_id}. "
                "Please analyze the channel first using /analyze-channel.",
            )

        competitors = find_competitors(profile, exclude_channel_id=body.channel_id)
        logger.info(
            "POST /find-competitors SUCCESS - channel_id=%s, found=%d competitors",
            body.channel_id,
            len(competitors),
        )
        return competitors
    except HTTPException:
        raise
    except ValueError as exc:
        logger.error("POST /find-competitors BAD_INPUT - %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("POST /find-competitors ERROR - %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(exc)}",
        ) from exc


@app.post("/search-topic", response_model=SearchTopicResponse)
@limiter.limit("10/minute")
async def search_topic_endpoint(
    request: Request,
    body: SearchTopicRequest,
) -> SearchTopicResponse:
    """Search for content on YouTube and Reddit for a given topic.

    Returns a unified feed of trending/popular/underrated content from both platforms,
    along with AI-generated content angle suggestions tailored to the channel.
    """
    logger.info(
        "POST /search-topic - channel_id=%s, topic=%s, competitors=%d",
        body.channel_id,
        body.topic,
        len(body.competitor_channel_ids),
    )

    try:
        profile = get_cached_channel_profile(body.channel_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Channel profile not found for channel_id={body.channel_id}. "
                "Please analyze the channel first using /analyze-channel.",
            )

        classified_results, insight = search_topic_with_insights(
            profile,
            body.topic,
            body.competitor_channel_ids,
            subreddits=None,
        )

        logger.info(
            "POST /search-topic SUCCESS - channel_id=%s, topic=%s, results=%d",
            body.channel_id,
            body.topic,
            len(classified_results),
        )
        return SearchTopicResponse(results=classified_results, insight=insight)
    except HTTPException:
        raise
    except ValueError as exc:
        logger.error("POST /search-topic BAD_INPUT - %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("POST /search-topic ERROR - %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(exc)}",
        ) from exc


@app.get("/health")
async def health_check():
    """Simple liveness probe."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Export Endpoints (Pro+ plan)
# ---------------------------------------------------------------------------


@app.get("/api/analyze/{channel_id}/export")
async def export_analysis(
    channel_id: str,
    format: str = "csv",
    user: User = Depends(get_current_user),
):
    """Export analysis data as CSV or PDF (Pro+ plan required)."""
    if user.plan not in ("pro", "business"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Export requires Pro or Business plan",
        )

    profile = get_cached_channel_profile(channel_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if format == "csv":
        import csv
        import io
        from fastapi.responses import StreamingResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Field", "Value"])
        writer.writerow(["Channel", profile.title])
        writer.writerow(["Subscribers", profile.subscriber_count])
        writer.writerow(["Niche", profile.niche])
        writer.writerow(["Content Style", profile.content_style])
        writer.writerow(["Target Audience", profile.target_audience])
        for i, rec in enumerate(profile.content_recommendations, 1):
            writer.writerow([f"Recommendation {i}", rec])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=analysis_{channel_id}.csv"},
        )

    elif format == "pdf":
        try:
            from fastapi.responses import StreamingResponse
            import io

            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet

            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            styles = getSampleStyleSheet()
            story = []

            story.append(Paragraph(f"Channel: {profile.title}", styles["Title"]))
            story.append(Spacer(1, 12))
            story.append(Paragraph(f"<b>Niche:</b> {profile.niche}", styles["Normal"]))
            story.append(Paragraph(f"<b>Subscribers:</b> {profile.subscriber_count:,}", styles["Normal"]))
            story.append(Paragraph(f"<b>Content Style:</b> {profile.content_style}", styles["Normal"]))
            story.append(Paragraph(f"<b>Target Audience:</b> {profile.target_audience}", styles["Normal"]))
            story.append(Paragraph(f"<b>AI Summary:</b> {profile.ai_summary}", styles["Normal"]))
            story.append(Spacer(1, 12))

            if profile.content_recommendations:
                story.append(Paragraph("<b>Content Recommendations:</b>", styles["Heading2"]))
                for rec in profile.content_recommendations:
                    story.append(Paragraph(f"&bull; {rec}", styles["Normal"]))

            doc.build(story)
            buffer.seek(0)

            return StreamingResponse(
                buffer,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename=analysis_{channel_id}.pdf"},
            )
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="PDF export requires reportlab. Install with: pip install reportlab",
            )

    else:
        raise HTTPException(status_code=400, detail="Format must be 'csv' or 'pdf'")


# ---------------------------------------------------------------------------
# Static File Serving — Landing page at /, App at /app
# ---------------------------------------------------------------------------

static_dir = Path(__file__).parent.parent / "static"


@app.get("/app")
async def serve_app():
    """Serve the main application UI."""
    return FileResponse(str(static_dir / "index.html"))


# Serve landing page and other static files at root
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
