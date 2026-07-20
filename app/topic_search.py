"""Topic search — queries YouTube for content matching a given topic.

Phase 6 implementation.  Combines global and competitor-scoped YouTube search
into a unified ``ContentResult`` feed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from googleapiclient.discovery import build

from app.config import settings
from app.db import get_cached_topic_search, save_topic_search
from app.models import ChannelProfile, ContentResult, TopicInsight

logger = logging.getLogger(__name__)

_YOUTUBE_GLOBAL_LIMIT = 20
_YOUTUBE_COMPETITOR_LIMIT = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_youtube_client():
    """Construct an authenticated YouTube Data API client."""
    return build("youtube", "v3", developerKey=settings.YOUTUBE_API_KEY)


def _parse_youtube_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp from the YouTube API."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------


def search_youtube(topic: str, competitor_channel_ids: list[str]) -> list[ContentResult]:
    """Search YouTube globally and within competitor channels for *topic*.

    Deduplicates by video ID, fetches view/like counts, and returns
    ``ContentResult`` objects.  Individual search failures are logged and skipped.
    """
    youtube = _build_youtube_client()
    snippets: dict[str, dict] = {}

    def _collect_search_results(**kwargs) -> None:
        try:
            response = (
                youtube.search()
                .list(part="snippet", q=topic, type="video", **kwargs)
                .execute()
            )
            for item in response.get("items", []):
                video_id = item["id"]["videoId"]
                snippets.setdefault(video_id, item["snippet"])
        except Exception as exc:
            logger.warning("YouTube search failed (%s): %s", kwargs, exc)

    _collect_search_results(maxResults=_YOUTUBE_GLOBAL_LIMIT)

    for channel_id in competitor_channel_ids:
        _collect_search_results(
            channelId=channel_id,
            maxResults=_YOUTUBE_COMPETITOR_LIMIT,
        )

    if not snippets:
        return []

    results: list[ContentResult] = []
    video_ids = list(snippets.keys())

    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        try:
            response = (
                youtube.videos()
                .list(part="snippet,statistics", id=",".join(batch))
                .execute()
            )
        except Exception as exc:
            logger.warning("YouTube video details fetch failed: %s", exc)
            continue

        for item in response.get("items", []):
            video_id = item["id"]
            snippet = item.get("snippet", snippets.get(video_id, {}))
            stats = item.get("statistics", {})
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))

            results.append(
                ContentResult(
                    platform="youtube",
                    title=snippet.get("title", ""),
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    engagement_score=float(views),
                    published_at=_parse_youtube_timestamp(
                        snippet.get("publishedAt", "1970-01-01T00:00:00Z")
                    ),
                    source=snippet.get("channelTitle", "Unknown"),
                    raw_metrics={"views": views, "likes": likes},
                )
            )

    return results


# ---------------------------------------------------------------------------
# Unified feed
# ---------------------------------------------------------------------------


def search_topic(
    topic: str,
    competitor_channel_ids: list[str],
    subreddits: list[str] | None = None,
) -> list[ContentResult]:
    """Search YouTube for *topic* and return a result list.

    Returns partial results if search fails or returns zero items.
    This function does not use the cache — see ``search_topic_with_insights``.
    """
    results: list[ContentResult] = []

    try:
        results.extend(search_youtube(topic, competitor_channel_ids))
    except Exception as exc:
        logger.warning("YouTube topic search failed: %s", exc)

    return results


def search_topic_with_insights(
    profile: ChannelProfile,
    topic: str,
    competitor_channel_ids: list[str],
    subreddits: list[str] | None = None,
    *,
    max_age_hours: int = 24,
    use_cache: bool = True,
) -> tuple[list[ContentResult], TopicInsight]:
    """Search a topic, classify results, and generate AI insights with caching.

    On a cache hit within *max_age_hours*, returns stored results and insights
    without calling YouTube or Gemini.
    """
    # Lazy imports avoid circular dependencies at module load time.
    from app.ai_reasoning import generate_insights
    from app.classifier import classify_results

    channel_id = profile.channel_id
    normalized_topic = topic.strip()

    if use_cache:
        cached = get_cached_topic_search(channel_id, normalized_topic, max_age_hours)
        if cached is not None:
            logger.info(
                "Topic search cache HIT for channel_id=%s topic=%r "
                "(external APIs skipped)",
                channel_id,
                normalized_topic,
            )
            return cached

    logger.info(
        "Topic search cache MISS for channel_id=%s topic=%r — "
        "calling YouTube/Gemini APIs",
        channel_id,
        normalized_topic,
    )

    results = classify_results(
        search_topic(normalized_topic, competitor_channel_ids, subreddits)
    )
    insight = generate_insights(profile, normalized_topic, results)

    if use_cache:
        save_topic_search(channel_id, normalized_topic, results, insight)

    return results, insight
