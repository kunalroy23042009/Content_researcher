"""Competitor finder — discovers related YouTube channels in the same niche.

Phase 5 implementation.  Uses Gemini to generate realistic search queries a
viewer in the niche would type, runs them through YouTube search, deduplicates
channels, ranks by subscriber-count proximity, and returns the top 10.
"""

from __future__ import annotations

import json
import logging
import math

from google import genai
from googleapiclient.discovery import build

from app.config import settings
from app.models import ChannelProfile, CompetitorChannel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_youtube_client():
    """Construct an authenticated YouTube Data API client."""
    return build("youtube", "v3", developerKey=settings.YOUTUBE_API_KEY)


def _get_gemini_client() -> genai.Client:
    """Return a configured Gemini client."""
    return genai.Client(api_key=settings.GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# Step 1 — AI-generated search queries
# ---------------------------------------------------------------------------


def generate_search_queries(profile: ChannelProfile) -> list[str]:
    """Ask Gemini for 5-8 realistic YouTube search queries a viewer in this niche would type.

    Falls back to simple heuristic queries if Gemini is unavailable.
    """
    prompt = f"""You are a YouTube search expert.  Given the following channel profile,
generate 5 to 8 realistic YouTube search queries that a viewer interested in this
exact niche would type to find similar content or channels.

Return ONLY a JSON array of strings — no markdown, no code fences, no explanation.
Example: ["query one", "query two", ...]

Channel profile:
- Title: {profile.title}
- Niche: {profile.niche}
- Topics: {json.dumps(profile.topics)}
- Content style: {profile.content_style}
- Target audience: {profile.target_audience}
- Recent video titles: {json.dumps(profile.recent_video_titles[:8])}
"""

    try:
        client = _get_gemini_client()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        text = response.text.strip()
        # Strip possible markdown fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        queries = json.loads(text)
        if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
            return queries[:8]
    except Exception as exc:
        logger.warning("Gemini query generation failed: %s", exc)

    # Fallback: build simple queries from profile data
    fallback = []
    if profile.niche:
        fallback.append(profile.niche)
    for topic in profile.topics[:4]:
        fallback.append(topic)
    if profile.title:
        fallback.append(f"channels like {profile.title}")
    return fallback or ["youtube creator"]


# ---------------------------------------------------------------------------
# Step 2 — Search, deduplicate, rank, return
# ---------------------------------------------------------------------------


def find_competitors(
    profile: ChannelProfile,
    exclude_channel_id: str,
    max_results: int = 10,
) -> list[CompetitorChannel]:
    """Discover competitor channels for *profile*.

    1. Generate niche-aware search queries via Gemini.
    2. Run each query through ``youtube.search.list`` (type=video).
    3. Collect unique channel IDs from the results (excluding *exclude_channel_id*).
    4. Fetch subscriber counts via ``youtube.channels.list``.
    5. Rank by subscriber-count proximity (log-ratio) — channels closest in size
       to the source channel score highest.
    6. Return up to *max_results* ``CompetitorChannel`` objects.
    """
    youtube = _build_youtube_client()

    # --- 1. Generate search queries ---
    queries = generate_search_queries(profile)
    logger.info("Competitor search queries: %s", queries)

    # --- 2. Collect candidate channel IDs ---
    candidate_ids: dict[str, int] = {}  # channel_id -> occurrence count

    for query in queries:
        try:
            response = (
                youtube.search()
                .list(part="snippet", q=query, type="video", maxResults=10)
                .execute()
            )
            for item in response.get("items", []):
                cid = item["snippet"]["channelId"]
                if cid != exclude_channel_id:
                    candidate_ids[cid] = candidate_ids.get(cid, 0) + 1
        except Exception as exc:
            logger.warning("YouTube search failed for query '%s': %s", query, exc)

    if not candidate_ids:
        logger.info("No competitor candidates found.")
        return []

    # --- 3. Fetch channel details in batches of 50 ---
    all_ids = list(candidate_ids.keys())
    channel_details: dict[str, dict] = {}

    for i in range(0, len(all_ids), 50):
        batch = all_ids[i : i + 50]
        try:
            response = (
                youtube.channels()
                .list(part="snippet,statistics", id=",".join(batch))
                .execute()
            )
            for ch in response.get("items", []):
                channel_details[ch["id"]] = ch
        except Exception as exc:
            logger.warning("Channel details fetch failed: %s", exc)

    # --- 4. Build CompetitorChannel objects with relevance ranking ---
    source_subs = max(profile.subscriber_count, 1)  # avoid log(0)
    competitors: list[tuple[float, CompetitorChannel]] = []

    for cid, ch in channel_details.items():
        subs = int(ch.get("statistics", {}).get("subscriberCount", 0))
        title = ch.get("snippet", {}).get("title", "Unknown")

        # Relevance score: lower is better
        # Uses log-ratio so 10k vs 20k is treated similarly to 100k vs 200k
        log_ratio = abs(math.log10(max(subs, 1)) - math.log10(source_subs))

        # Bonus for channels that appeared in multiple search queries
        occurrence_bonus = candidate_ids.get(cid, 1)
        score = log_ratio - (occurrence_bonus * 0.15)

        # Human-readable relevance note
        if subs == 0:
            size_note = "subscriber count hidden"
        elif log_ratio < 0.2:
            size_note = "very similar size"
        elif log_ratio < 0.5:
            size_note = "similar size"
        elif subs > source_subs:
            size_note = "larger channel"
        else:
            size_note = "smaller channel"

        relevance_parts = [size_note]
        if occurrence_bonus > 1:
            relevance_parts.append(f"appeared in {occurrence_bonus} queries")

        competitor = CompetitorChannel(
            channel_id=cid,
            title=title,
            subscriber_count=subs,
            relevance_note=", ".join(relevance_parts),
        )
        competitors.append((score, competitor))

    # Sort by score ascending (lower = more relevant)
    competitors.sort(key=lambda x: x[0])

    return [c for _, c in competitors[:max_results]]
