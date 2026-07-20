"""Channel analyzer — fetches YouTube channel data and builds a niche profile using AI.

Phase 4 implementation.  Accepts a YouTube channel URL or ID, pulls metadata +
recent videos via the YouTube Data API, then asks AI to produce a structured
niche profile with detailed, actionable insights.
"""

from __future__ import annotations

import json
import logging
import re

from googleapiclient.discovery import build

from app.ai_provider import ComplexityLevel, generate_ai_response
from app.config import settings
from app.db import (
    get_cached_channel_profile,
    get_cached_channel_profile_by_url,
    save_channel_profile,
)
from app.models import ChannelProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CHANNEL_ID_RE = re.compile(r"UC[\w-]{22}")
_HANDLE_RE = re.compile(r"@([\w.-]+)")


def _extract_channel_identifier(url_or_id: str) -> tuple[str, str]:
    """Return (kind, value) where kind is 'id', 'forHandle', or 'forUsername'."""
    text = url_or_id.strip().rstrip("/")

    m = _CHANNEL_ID_RE.search(text)
    if m:
        return ("id", m.group(0))

    m = _HANDLE_RE.search(text)
    if m:
        return ("forHandle", f"@{m.group(1)}")

    for prefix, kind in [("/c/", "forUsername"), ("/user/", "forUsername")]:
        if prefix in text:
            name = text.split(prefix, 1)[1].split("/")[0].split("?")[0]
            return (kind, name)

    return ("id", text)


def _build_youtube_client():
    return build("youtube", "v3", developerKey=settings.YOUTUBE_API_KEY)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_channel(
    url_or_id: str,
    *,
    max_age_hours: int = 24,
    use_cache: bool = True,
) -> ChannelProfile:
    """Fetch channel metadata + recent videos, then build an AI niche profile."""
    if use_cache:
        kind, value = _extract_channel_identifier(url_or_id)
        if kind == "id" and _CHANNEL_ID_RE.fullmatch(value):
            cached = get_cached_channel_profile(value, max_age_hours)
            if cached is not None:
                logger.info("Channel profile cache HIT for channel_id=%s", value)
                return cached

        cached = get_cached_channel_profile_by_url(url_or_id, max_age_hours)
        if cached is not None:
            logger.info("Channel profile cache HIT for url=%s", url_or_id.strip())
            return cached

    logger.info("Channel profile cache MISS for %s — calling YouTube/Gemini APIs", url_or_id.strip())
    profile = _analyze_channel_live(url_or_id)
    if use_cache:
        save_channel_profile(profile, url=url_or_id.strip())
    return profile


def _analyze_channel_live(url_or_id: str) -> ChannelProfile:
    """Fetch and enrich a channel profile without consulting the cache."""
    youtube = _build_youtube_client()

    kind, value = _extract_channel_identifier(url_or_id)
    request = youtube.channels().list(part="snippet,statistics", **{kind: value})
    response = request.execute()

    if not response.get("items"):
        raise ValueError(f"No YouTube channel found for '{url_or_id}'")

    ch = response["items"][0]
    snippet = ch["snippet"]
    stats = ch["statistics"]
    channel_id = ch["id"]

    # Fetch recent videos with detailed stats
    search_resp = (
        youtube.search()
        .list(
            part="snippet",
            channelId=channel_id,
            order="date",
            maxResults=15,
            type="video",
        )
        .execute()
    )

    video_ids = [item["id"]["videoId"] for item in search_resp.get("items", [])]
    recent_titles = [item["snippet"]["title"] for item in search_resp.get("items", [])]

    # Fetch detailed video statistics
    video_stats = {}
    if video_ids:
        videos_resp = (
            youtube.videos()
            .list(part="statistics", id=",".join(video_ids[:10]))
            .execute()
        )
        for item in videos_resp.get("items", []):
            video_stats[item["id"]] = item["statistics"]

    # Calculate enhanced metrics
    subscriber_count = int(stats.get("subscriberCount", 0))
    video_count = int(stats.get("videoCount", 0))
    view_count = int(stats.get("viewCount", 0))

    avg_views = view_count / video_count if video_count > 0 else 0

    total_likes = 0
    total_comments = 0
    total_recent_views = 0

    for vid in video_ids[:10]:
        if vid in video_stats:
            vstats = video_stats[vid]
            total_likes += int(vstats.get("likeCount", 0))
            total_comments += int(vstats.get("commentCount", 0))
            total_recent_views += int(vstats.get("viewCount", 0))

    engagement_rate = 0.0
    if total_recent_views > 0:
        engagement_rate = ((total_likes + total_comments) / total_recent_views) * 100

    # Channel tier classification
    if subscriber_count < 1000:
        channel_tier = "Nano"
    elif subscriber_count < 10000:
        channel_tier = "Micro"
    elif subscriber_count < 100000:
        channel_tier = "Mid-Tier"
    elif subscriber_count < 1000000:
        channel_tier = "Macro"
    else:
        channel_tier = "Mega"

    # Build base profile
    profile = ChannelProfile(
        channel_id=channel_id,
        title=snippet.get("title", ""),
        description=snippet.get("description", ""),
        subscriber_count=subscriber_count,
        video_count=video_count,
        view_count=view_count,
        recent_video_titles=recent_titles,
        average_views_per_video=avg_views,
        engagement_rate=engagement_rate,
        channel_tier=channel_tier,
    )

    profile = _enrich_with_ai(profile)

    return profile


def _enrich_with_ai(profile: ChannelProfile) -> ChannelProfile:
    """Use AI to determine niche, topics, content style, and detailed insights."""
    prompt = f"""You are an expert YouTube strategist analyzing a channel for growth opportunities.

Analyze the channel below and return ONLY a raw JSON object (no markdown, no code fences) with exactly these keys:

{{
  "niche": "primary niche in 2-5 words",
  "topics": ["3-6 main content topics"],
  "content_style": "brief description of the channel's content style, tone, and format",
  "target_audience": "specific description of who watches this channel (demographics, interests, pain points)",
  "ai_summary": "3-4 sentences analyzing the channel's strengths, weaknesses, and market position. Be specific — mention actual video performance patterns, content gaps, and what makes this channel unique or generic. Don't just describe; analyze.",
  "upload_frequency": "estimated upload frequency (daily, 2-3x/week, weekly, bi-weekly, monthly, or sporadic)",
  "growth_potential": "rate as 'Very High', 'High', 'Medium', or 'Low' followed by a brief reason (e.g., 'High — strong engagement but inconsistent upload schedule limits momentum')",
  "content_recommendations": [
    "5-7 specific, actionable content ideas. Each should include: WHAT to make, WHY it fits this channel, and HOW to execute it differently from competitors. Reference the channel's actual topics and style. Do not give generic advice like 'make better thumbnails' — be specific like 'Create a "Budget vs Premium" comparison series comparing $200 vs $2000 [niche] items since your audience clearly values cost-performance analysis'."
  ],
  "optimization_tips": [
    "5-7 specific, actionable optimization tips. Each should address a concrete aspect: titles, thumbnails, descriptions, tags, CTAs, pacing, SEO, community engagement, or analytics. Reference the channel's actual data. For example: 'Your recent titles average 8 words but top-performing titles in your niche use 5-6 words with numbers — try "5 Best [X] Under $Y" format'."
  ]
}}

Channel info:
- Title: {profile.title}
- Description: {profile.description[:600]}
- Subscribers: {profile.subscriber_count:,}
- Total videos: {profile.video_count}
- Total views: {profile.view_count:,}
- Average views per video: {profile.average_views_per_video:,.0f}
- Engagement rate: {profile.engagement_rate:.2f}%
- Channel tier: {profile.channel_tier}
- Recent video titles: {json.dumps(profile.recent_video_titles[:10])}

Important:
- Be genuinely insightful, not generic. Reference actual patterns from the data above.
- If the channel has low engagement, say why and what specific content could fix it.
- If the channel has high engagement, identify what's working so they can double down.
- Content recommendations should be specific enough that the creator can start working on them immediately.
- Optimization tips should reference actual numbers from the channel's data when possible.
"""

    try:
        text = generate_ai_response(
            prompt=prompt,
            complexity=ComplexityLevel.HIGH,
        )

        # Strip possible markdown fences
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        data = json.loads(text)
        profile.niche = data.get("niche", "")
        profile.topics = data.get("topics", [])
        profile.content_style = data.get("content_style", "")
        profile.target_audience = data.get("target_audience", "")
        profile.ai_summary = data.get("ai_summary", "")
        profile.upload_frequency = data.get("upload_frequency", "unknown")
        profile.growth_potential = data.get("growth_potential", "unknown")
        profile.content_recommendations = data.get("content_recommendations", [])
        profile.optimization_tips = data.get("optimization_tips", [])
    except Exception as exc:
        logger.warning("AI niche profiling failed: %s", exc)
        profile.niche = "unknown"
        profile.ai_summary = "AI profiling unavailable. Check your API keys and try again."
        profile.upload_frequency = "unknown"
        profile.growth_potential = "unknown"

    return profile
