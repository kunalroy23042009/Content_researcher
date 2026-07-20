"""Channel analyzer — fetches YouTube channel data and builds a niche profile using AI.

Phase 4 implementation.  Accepts a YouTube channel URL or ID, pulls metadata +
recent videos via the YouTube Data API, then asks Gemini to produce a structured
niche profile.
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
    """Return (kind, value) where kind is 'id', 'forHandle', or 'forUsername'.

    Supports URLs like:
        https://www.youtube.com/channel/UC...
        https://www.youtube.com/@handle
        https://www.youtube.com/c/CustomName
        https://www.youtube.com/user/Username
        or a bare channel ID / @handle
    """
    text = url_or_id.strip().rstrip("/")

    # Direct channel ID
    m = _CHANNEL_ID_RE.search(text)
    if m:
        return ("id", m.group(0))

    # @handle in URL or standalone
    m = _HANDLE_RE.search(text)
    if m:
        return ("forHandle", f"@{m.group(1)}")

    # /c/CustomName or /user/Username
    for prefix, kind in [("/c/", "forUsername"), ("/user/", "forUsername")]:
        if prefix in text:
            name = text.split(prefix, 1)[1].split("/")[0].split("?")[0]
            return (kind, name)

    # Fallback: treat the whole thing as a channel ID
    return ("id", text)


def _build_youtube_client():
    """Construct an authenticated YouTube Data API client."""
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
    """Fetch channel metadata + recent videos, then build an AI niche profile.

    Checks the local SQLite cache first.  On a cache miss, calls YouTube and
    Gemini, then persists the result for *max_age_hours*.

    Parameters
    ----------
    url_or_id:
        A YouTube channel URL, @handle, or raw channel ID.
    max_age_hours:
        Maximum cache age before a fresh API call is made.
    use_cache:
        When False, always call external APIs (useful in tests).

    Returns
    -------
    ChannelProfile with all fields populated (including AI-generated niche info).
    """
    if use_cache:
        kind, value = _extract_channel_identifier(url_or_id)
        if kind == "id" and _CHANNEL_ID_RE.fullmatch(value):
            cached = get_cached_channel_profile(value, max_age_hours)
            if cached is not None:
                logger.info(
                    "Channel profile cache HIT for channel_id=%s (external APIs skipped)",
                    value,
                )
                return cached

        cached = get_cached_channel_profile_by_url(url_or_id, max_age_hours)
        if cached is not None:
            logger.info(
                "Channel profile cache HIT for url=%s (external APIs skipped)",
                url_or_id.strip(),
            )
            return cached

    logger.info(
        "Channel profile cache MISS for %s — calling YouTube/Gemini APIs",
        url_or_id.strip(),
    )
    profile = _analyze_channel_live(url_or_id)
    if use_cache:
        save_channel_profile(profile, url=url_or_id.strip())
    return profile


def _analyze_channel_live(url_or_id: str) -> ChannelProfile:
    """Fetch and enrich a channel profile without consulting the cache."""
    youtube = _build_youtube_client()

    # --- Resolve to channel resource ---
    kind, value = _extract_channel_identifier(url_or_id)
    request = youtube.channels().list(part="snippet,statistics", **{kind: value})
    response = request.execute()

    if not response.get("items"):
        raise ValueError(f"No YouTube channel found for '{url_or_id}'")

    ch = response["items"][0]
    snippet = ch["snippet"]
    stats = ch["statistics"]
    channel_id = ch["id"]

    # --- Fetch recent videos with detailed stats ---
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
    
    # Fetch detailed video statistics for engagement calculation
    video_stats = {}
    if video_ids:
        videos_resp = (
            youtube.videos()
            .list(part="statistics", id=",".join(video_ids[:10]))
            .execute()
        )
        for item in videos_resp.get("items", []):
            video_stats[item["id"]] = item["statistics"]

    # --- Calculate enhanced metrics ---
    subscriber_count = int(stats.get("subscriberCount", 0))
    video_count = int(stats.get("videoCount", 0))
    view_count = int(stats.get("viewCount", 0))
    
    # Average views per video
    avg_views = view_count / video_count if video_count > 0 else 0
    
    # Engagement rate (likes + comments / views) for recent videos
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

    # --- Build base profile ---
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

    # --- AI niche profiling via Gemini ---
    profile = _enrich_with_ai(profile)

    return profile


def _enrich_with_ai(profile: ChannelProfile) -> ChannelProfile:
    """Use AI to determine niche, topics, content style, target audience, and enhanced insights."""
    prompt = f"""You are a YouTube analyst. Analyze this channel and return a JSON object
with exactly these keys (no markdown, no code fences, just raw JSON):
{{
  "niche": "<primary niche in 2-5 words>",
  "topics": ["<topic1>", "<topic2>", ...],  // 3-6 main topics
  "content_style": "<brief description of content style>",
  "target_audience": "<who watches this channel>",
  "ai_summary": "<2-3 sentence overall summary>",
  "upload_frequency": "<estimated upload frequency like 'daily', 'weekly', 'bi-weekly'>",
  "growth_potential": "<assessment of growth potential: 'high', 'medium', or 'low' with brief reason>",
  "content_recommendations": ["<recommendation1>", "<recommendation2>", ...],  // 3-5 specific content ideas
  "optimization_tips": ["<tip1>", "<tip2>", ...]  // 3-5 actionable optimization tips
}}

Channel info:
- Title: {profile.title}
- Description: {profile.description[:500]}
- Subscribers: {profile.subscriber_count:,}
- Total videos: {profile.video_count}
- Total views: {profile.view_count:,}
- Average views per video: {profile.average_views_per_video:,.0f}
- Engagement rate: {profile.engagement_rate:.2f}%
- Channel tier: {profile.channel_tier}
- Recent video titles: {json.dumps(profile.recent_video_titles[:10])}
"""

    try:
        text = generate_ai_response(
            prompt=prompt,
            complexity=ComplexityLevel.HIGH,  # Channel analysis is complex
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
        profile.ai_summary = "AI profiling unavailable."
        profile.upload_frequency = "unknown"
        profile.growth_potential = "unknown"

    return profile
