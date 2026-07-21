"""Channel analyzer — fetches YouTube channel data and builds a niche profile using AI.

Fetches up to 50 recent videos with full statistics, analyzes performance
patterns (overperformers vs underperformers, title patterns, posting schedule),
and uses AI to generate content recommendations based on the creator's
actual content history.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone

from googleapiclient.discovery import build

from app.ai_provider import ComplexityLevel, generate_ai_response
from app.config import settings
from app.db import (
    get_cached_channel_profile,
    get_cached_channel_profile_by_url,
    save_channel_profile,
)
from app.models import ChannelProfile, VideoPerformance

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CHANNEL_ID_RE = re.compile(r"UC[\w-]{22}")
_HANDLE_RE = re.compile(r"@([\w.-]+)")


def _extract_channel_identifier(url_or_id: str) -> tuple[str, str]:
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
    """Build YouTube API client, raising a clear error if the API key is missing."""
    if not settings.YOUTUBE_API_KEY:
        raise ValueError(
            "YOUTUBE_API_KEY is not set. "
            "Add it as an environment variable in your Render dashboard → Environment tab."
        )
    return build("youtube", "v3", developerKey=settings.YOUTUBE_API_KEY, cache_discovery=False)


def _iso_to_seconds(duration: str) -> int:
    """Parse ISO 8601 duration (PT1H2M3S) to seconds."""
    import isodate
    try:
        return int(isodate.parse_duration(duration).total_seconds())
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Video performance analysis
# ---------------------------------------------------------------------------

def _analyze_video_performance(video_data: list[dict], avg_views: float) -> dict:
    """Analyze video performance patterns from detailed video stats.

    Returns dict with:
    - top_videos: list of (title, views, likes, comments, ratio) sorted by views
    - underperformers: list of videos that performed below average
    - title_word_freq: most common words in top-performing titles
    - avg_title_length: average title length of top videos
    - posting_days: most common days of week for top videos
    """
    if not video_data or avg_views <= 0:
        return {
            "top_videos": [],
            "underperformers": [],
            "title_word_freq": [],
            "avg_title_length": 0,
            "posting_days": [],
        }

    performances = []
    for v in video_data:
        views = int(v.get("viewCount", 0))
        likes = int(v.get("likeCount", 0))
        comments = int(v.get("commentCount", 0))
        title = v.get("title", "")
        ratio = views / avg_views if avg_views > 0 else 0.0
        published = v.get("publishedAt", "")

        performances.append(
            VideoPerformance(
                title=title,
                video_id=v.get("id", ""),
                views=views,
                likes=likes,
                comments=comments,
                published_at=published,
                performance_ratio=ratio,
            )
        )

    # Sort by views
    sorted_by_views = sorted(performances, key=lambda p: p.views, reverse=True)
    top_videos = sorted_by_views[:5]

    # Underperformers: below 50% of average
    underperformers = [p for p in sorted_by_views if p.views < avg_views * 0.5][-3:]

    # Title word frequency in top videos
    stop_words = {"the", "a", "an", "to", "in", "of", "for", "and", "on", "with", "how", "your", "my", "is", "are", "you", "this", "that"}
    word_freq = Counter()
    for p in top_videos:
        words = re.findall(r"[a-zA-Z]+", p.title.lower())
        for w in words:
            if w not in stop_words and len(w) > 2:
                word_freq[w] += 1
    title_word_freq = word_freq.most_common(10)

    # Average title length of top videos
    top_title_lengths = [len(p.title.split()) for p in top_videos]
    avg_title_length = sum(top_title_lengths) / len(top_title_lengths) if top_title_lengths else 0

    # Posting days from top videos
    posting_days = []
    for p in top_videos:
        if p.published_at:
            try:
                dt = datetime.fromisoformat(p.published_at.replace("Z", "+00:00"))
                posting_days.append(dt.strftime("%A"))
            except Exception:
                pass
    day_freq = Counter(posting_days).most_common(3)

    return {
        "top_videos": top_videos,
        "underperformers": underperformers,
        "title_word_freq": title_word_freq,
        "avg_title_length": avg_title_length,
        "posting_days": day_freq,
    }


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

    # --- Resolve channel resource ---
    kind, value = _extract_channel_identifier(url_or_id)
    request = youtube.channels().list(part="snippet,statistics", **{kind: value})
    response = request.execute()

    if not response.get("items"):
        raise ValueError(f"No YouTube channel found for '{url_or_id}'")

    ch = response["items"][0]
    snippet = ch["snippet"]
    stats = ch["statistics"]
    channel_id = ch["id"]

    # --- Fetch recent videos (up to 50) ---
    all_video_items = []
    search_resp = (
        youtube.search()
        .list(
            part="snippet",
            channelId=channel_id,
            order="date",
            maxResults=50,
            type="video",
        )
        .execute()
    )
    all_video_items = search_resp.get("items", [])

    # Paginate if there are more results (get up to 50 total)
    while len(all_video_items) < 50 and "nextPageToken" in search_resp:
        search_resp = (
            youtube.search()
            .list(
                part="snippet",
                channelId=channel_id,
                order="date",
                maxResults=50 - len(all_video_items),
                type="video",
                pageToken=search_resp["nextPageToken"],
            )
            .execute()
        )
        all_video_items.extend(search_resp.get("items", []))

    video_ids = [item["id"]["videoId"] for item in all_video_items]
    recent_titles = [item["snippet"]["title"] for item in all_video_items[:15]]

    # --- Fetch detailed video statistics (in batches of 50) ---
    video_details = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        try:
            videos_resp = (
                youtube.videos()
                .list(part="snippet,statistics,contentDetails", id=",".join(batch))
                .execute()
            )
            for item in videos_resp.get("items", []):
                vstats = item.get("statistics", {})
                vsnippet = item.get("snippet", {})
                content_details = item.get("contentDetails", {})
                video_details.append({
                    "id": item["id"],
                    "title": vsnippet.get("title", ""),
                    "publishedAt": vsnippet.get("publishedAt", ""),
                    "viewCount": vstats.get("viewCount", 0),
                    "likeCount": vstats.get("likeCount", 0),
                    "commentCount": vstats.get("commentCount", 0),
                    "duration": content_details.get("duration", ""),
                })
        except Exception as exc:
            logger.warning("Failed to fetch video details batch: %s", exc)

    # --- Calculate enhanced metrics ---
    subscriber_count = int(stats.get("subscriberCount", 0))
    video_count = int(stats.get("videoCount", 0))
    view_count = int(stats.get("viewCount", 0))

    avg_views = view_count / video_count if video_count > 0 else 0

    # Calculate engagement from recent videos
    total_likes = 0
    total_comments = 0
    total_recent_views = 0
    for v in video_details:
        total_likes += int(v.get("likeCount", 0))
        total_comments += int(v.get("commentCount", 0))
        total_recent_views += int(v.get("viewCount", 0))

    engagement_rate = 0.0
    if total_recent_views > 0:
        engagement_rate = ((total_likes + total_comments) / total_recent_views) * 100

    # Average duration of recent videos
    total_duration = 0
    durations_counted = 0
    for v in video_details:
        dur = _iso_to_seconds(v.get("duration", ""))
        if dur > 0:
            total_duration += dur
            durations_counted += 1
    avg_duration = total_duration / durations_counted if durations_counted > 0 else 0

    # Channel tier
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

    # --- Analyze video performance patterns ---
    perf_analysis = _analyze_video_performance(video_details, avg_views)

    # Calculate average views for recent videos specifically
    recent_avg_views = total_recent_views / len(video_details) if video_details else 0

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
        top_performing_videos=perf_analysis["top_videos"],
        underperforming_videos=perf_analysis["underperformers"],
        title_patterns=[f"{word} ({count}x)" for word, count in perf_analysis["title_word_freq"]],
    )

    # --- AI niche profiling ---
    profile = _enrich_with_ai(profile, {
        "recent_avg_views": recent_avg_views,
        "avg_duration": avg_duration,
        "avg_title_length": perf_analysis["avg_title_length"],
        "posting_days": perf_analysis["posting_days"],
        "title_word_freq": perf_analysis["title_word_freq"],
        "video_details": video_details,
    })

    return profile


def _enrich_with_ai(profile: ChannelProfile, extra_data: dict) -> ChannelProfile:
    """Use AI to determine niche, topics, content style, and detailed insights
    based on the creator's actual video performance data.
    """
    # Format top performing videos
    top_videos_text = ""
    if profile.top_performing_videos:
        top_videos_text = "\n".join([
            f"  {i+1}. \"{v.title}\" — {v.views:,} views, {v.likes:,} likes, "
            f"{v.comments:,} comments ({v.performance_ratio:.1f}x channel avg)"
            for i, v in enumerate(profile.top_performing_videos)
        ])

    # Format underperforming videos
    underperformers_text = ""
    if profile.underperforming_videos:
        underperformers_text = "\n".join([
            f"  {i+1}. \"{v.title}\" — {v.views:,} views ({v.performance_ratio:.1f}x avg)"
            for i, v in enumerate(profile.underperforming_videos)
        ])

    # Format title patterns
    title_patterns_text = ""
    if extra_data.get("title_word_freq"):
        title_patterns_text = ", ".join([
            f"'{word}' ({count}x)" for word, count in extra_data["title_word_freq"][:7]
        ])

    # Format posting days
    posting_days_text = ""
    if extra_data.get("posting_days"):
        posting_days_text = ", ".join([
            f"{day} ({count}x)" for day, count in extra_data["posting_days"]
        ])

    # Recent video stats summary
    video_stats_text = ""
    if extra_data.get("video_details"):
        recent_views = [int(v.get("viewCount", 0)) for v in extra_data["video_details"]]
        if recent_views:
            max_v = max(recent_views)
            min_v = min(recent_views)
            median_v = sorted(recent_views)[len(recent_views) // 2]
            video_stats_text = (
                f"Recent video stats (last {len(recent_views)} videos): "
                f"max={max_v:,}, min={min_v:,}, median={median_v:,} views"
            )

    avg_duration_min = extra_data.get("avg_duration", 0) / 60
    avg_title_len = extra_data.get("avg_title_length", 0)

    prompt = f"""You are an expert YouTube strategist analyzing a channel for growth opportunities.

You have access to the channel's actual video performance data — use it to give specific,
data-driven recommendations. Do NOT give generic advice.

Return ONLY a raw JSON object (no markdown, no code fences) with exactly these keys:

{{
  "niche": "primary niche in 2-5 words",
  "topics": ["3-6 main content topics"],
  "content_style": "brief description of the channel's content style, tone, and format",
  "target_audience": "specific description of who watches (demographics, interests, pain points)",
  "ai_summary": "3-5 sentences analyzing the channel's strengths, weaknesses, content patterns, and market position. Reference actual video performance data — which videos overperformed and WHY, what the engagement pattern tells you, and what the channel is doing right or wrong. Be analytical and specific.",
  "upload_frequency": "estimated upload frequency",
  "growth_potential": "rate as 'Very High', 'High', 'Medium', or 'Low' with brief reason",
  "best_topics": ["3-5 topics that drive the most engagement for THIS channel, based on their top-performing video titles"],
  "title_patterns": ["3-5 patterns identified in their best-performing titles (e.g., 'Uses numbers in titles', 'Asks questions', 'Includes price/cost', 'Contrarian framing')"],
  "content_gaps": ["3-5 topics the channel has NOT covered but should based on their niche and audience interests"],
  "content_recommendations": [
    "5-7 specific content ideas based on the creator's ACTUAL content performance. Each must: (a) reference a specific top-performing video or pattern from their data, (b) explain why it worked and how to replicate that success, (c) give a concrete title suggestion. Example: 'Your video \"X\" got 3x your average views — make a follow-up covering the next product tier up. Suggested title: \"5 [Category] at $X Price Point That Actually Work\"'. Do NOT give generic advice. Every recommendation must connect to their actual data."
  ],
  "optimization_tips": [
    "5-7 specific optimization tips referencing actual data. For example: 'Your top videos average {avg_title_len:.0f} words in the title but your underperformers average more — try shorter, punchier titles like your best one \"X\"'. Reference actual numbers, video titles, and performance ratios."
  ]
}}

Channel info:
- Title: {profile.title}
- Description: {profile.description[:600]}
- Subscribers: {profile.subscriber_count:,}
- Total videos: {profile.video_count}
- Total views: {profile.view_count:,}
- Average views per video (all-time): {profile.average_views_per_video:,.0f}
- Average views per recent video: {extra_data.get('recent_avg_views', 0):,.0f}
- Engagement rate: {profile.engagement_rate:.2f}%
- Channel tier: {profile.channel_tier}
- Average video duration: {avg_duration_min:.1f} minutes
- Average title length of top videos: {avg_title_len:.0f} words
- {video_stats_text}

TOP 5 PERFORMING VIDEOS (by views):
{top_videos_text or "  (no data)"}

UNDERPERFORMING VIDEOS (below 50% of average):
{underperformers_text or "  (none)"}

COMMON WORDS IN TOP-PERFORMING TITLES:
{title_patterns_text or "  (no data)"}

POSTING DAYS OF TOP VIDEOS:
{posting_days_text or "  (no data)"}

Recent video titles (most recent first):
{json.dumps(profile.recent_video_titles[:15])}

Critical requirements:
- Every recommendation MUST reference specific data from above (video titles, view counts, performance ratios, title patterns).
- Content recommendations should be sequels to or variations of their best-performing videos, or fill identified content gaps.
- If a video got 3x the channel average, explain WHY and recommend building on it.
- If underperformers share a pattern (too long, wrong topic, etc.), call it out.
- Title patterns should be actionable: "Use [pattern] because your top 3 videos all do this."
"""

    try:
        text = generate_ai_response(
            prompt=prompt,
            complexity=ComplexityLevel.HIGH,
        )

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
        profile.best_topics = data.get("best_topics", [])
        profile.title_patterns = data.get("title_patterns", [])
        profile.content_gaps = data.get("content_gaps", [])
        profile.content_recommendations = data.get("content_recommendations", [])
        profile.optimization_tips = data.get("optimization_tips", [])
    except Exception as exc:
        logger.warning("AI niche profiling failed: %s", exc)
        profile.niche = "unknown"
        profile.ai_summary = "AI profiling unavailable. Check your API keys and try again."
        profile.upload_frequency = "unknown"
        profile.growth_potential = "unknown"

    return profile
