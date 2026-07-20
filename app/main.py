"""
Creator Content Radar — FastAPI application entry point.

Mounts the API routes and serves the static frontend.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


from app.channel_analyzer import analyze_channel

from app.competitor_finder import find_competitors
from app.db import get_cached_channel_profile, init_db
from app.models import ChannelProfile, CompetitorChannel, ContentResult, TopicInsight
from app.topic_search import search_topic_with_insights

logger = logging.getLogger(__name__)


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
    """Initialize the SQLite cache on startup."""
    init_db()
    yield


app = FastAPI(
    title="Creator Content Radar",
    description="AI-powered YouTube channel analyzer and cross-platform content discovery tool",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@app.post("/analyze-channel", response_model=ChannelProfile)
async def analyze_channel_endpoint(request: AnalyzeChannelRequest) -> ChannelProfile:
    """Analyze a YouTube channel and return its niche profile.

    Accepts a YouTube channel URL or ID, fetches channel data via the YouTube Data API,
    and uses AI to determine niche, topics, content style, and target audience.
    """
    logger.info("POST /analyze-channel - channel_url=%s", request.channel_url)

    try:
        profile = analyze_channel(request.channel_url)
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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream API failure: {str(exc)}",
        ) from exc


@app.post("/find-competitors", response_model=list[CompetitorChannel])
async def find_competitors_endpoint(
    request: FindCompetitorsRequest,
) -> list[CompetitorChannel]:
    """Find competitor channels for a given YouTube channel.

    Returns a list of similar channels in the same niche, ranked by relevance
    based on subscriber count proximity and search query overlap.
    """
    logger.info("POST /find-competitors - channel_id=%s", request.channel_id)

    try:
        # First, get the channel profile from cache or analyze it
        profile = get_cached_channel_profile(request.channel_id)
        if profile is None:
            logger.error("POST /find-competitors CHANNEL_NOT_FOUND - channel_id=%s", request.channel_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Channel profile not found for channel_id={request.channel_id}. "
                "Please analyze the channel first using /analyze-channel.",
            )

        competitors = find_competitors(profile, exclude_channel_id=request.channel_id)
        logger.info(
            "POST /find-competitors SUCCESS - channel_id=%s, found=%d competitors",
            request.channel_id,
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
async def search_topic_endpoint(request: SearchTopicRequest) -> SearchTopicResponse:
    """Search for content on YouTube and Reddit for a given topic.

    Returns a unified feed of trending/popular/underrated content from both platforms,
    along with AI-generated content angle suggestions tailored to the channel.
    """
    logger.info(
        "POST /search-topic - channel_id=%s, topic=%s, competitors=%d",
        request.channel_id,
        request.topic,
        len(request.competitor_channel_ids),
    )

    try:
        # Get the channel profile from cache
        profile = get_cached_channel_profile(request.channel_id)
        if profile is None:
            logger.error("POST /search-topic CHANNEL_NOT_FOUND - channel_id=%s", request.channel_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Channel profile not found for channel_id={request.channel_id}. "
                "Please analyze the channel first using /analyze-channel.",
            )

        classified_results, insight = search_topic_with_insights(
            profile,
            request.topic,
            request.competitor_channel_ids,
            subreddits=None,
        )

        logger.info(
            "POST /search-topic SUCCESS - channel_id=%s, topic=%s, results=%d",
            request.channel_id,
            request.topic,
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


# Serve the static frontend
static_dir = Path(__file__).parent.parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
