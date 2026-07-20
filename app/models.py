"""Models — Pydantic/SQLModel definitions for channels, competitors, searches, and cached results."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Phase 4 — Channel analysis
# ---------------------------------------------------------------------------

class ChannelProfile(BaseModel):
    """Structured profile of a YouTube channel produced by the analyzer."""

    channel_id: str
    title: str
    description: str
    subscriber_count: int
    video_count: int
    view_count: int
    recent_video_titles: list[str] = []
    niche: str = ""
    topics: list[str] = []
    content_style: str = ""
    target_audience: str = ""
    ai_summary: str = ""
    # Enhanced metrics
    average_views_per_video: float = 0.0
    engagement_rate: float = 0.0
    upload_frequency: str = ""
    channel_tier: str = ""
    growth_potential: str = ""
    content_recommendations: list[str] = []
    optimization_tips: list[str] = []


# ---------------------------------------------------------------------------
# Phase 5 — Competitor discovery
# ---------------------------------------------------------------------------

class CompetitorChannel(BaseModel):
    """A competitor channel discovered for a given ChannelProfile."""

    channel_id: str
    title: str
    subscriber_count: int
    relevance_note: str


# ---------------------------------------------------------------------------
# Phase 6 — Topic search
# ---------------------------------------------------------------------------

class ContentResult(BaseModel):
    """A single piece of content discovered from YouTube or Reddit."""

    platform: Literal["youtube", "reddit"]
    title: str
    url: str
    engagement_score: float
    published_at: datetime
    source: str
    raw_metrics: dict
    classification: Literal["trending", "popular", "underrated", "none"] = "none"


# ---------------------------------------------------------------------------
# Phase 8 — AI reasoning
# ---------------------------------------------------------------------------

class TopicInsight(BaseModel):
    """AI-generated insights and content angles for a topic search."""

    summary: str
    content_angles: list[str]
    content_gap: str | None = None
