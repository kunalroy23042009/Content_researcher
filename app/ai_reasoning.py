"""AI reasoning — generates content angle suggestions using multiple AI providers.

Improved prompts for more specific, actionable insights that reference
actual search results and channel data.
"""

from __future__ import annotations

import json
import logging

from app.ai_provider import ComplexityLevel, generate_ai_response
from app.models import ChannelProfile, ContentResult, TopicInsight

logger = logging.getLogger(__name__)

MAX_RESULTS_FOR_PROMPT = 15
MAX_RETRY_ATTEMPTS = 2

FALLBACK_SUMMARY = (
    "AI insights could not be generated — the response could not be parsed. "
    "Try again in a moment."
)


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _select_results_for_prompt(results: list[ContentResult]) -> list[ContentResult]:
    """Pick the top results to include in the AI prompt (up to 15)."""
    if not results:
        return []

    classification_rank = {
        "trending": 0,
        "popular": 1,
        "underrated": 2,
        "none": 3,
    }

    ranked = sorted(
        results,
        key=lambda r: (
            classification_rank.get(r.classification, 3),
            -r.engagement_score,
        ),
    )
    return ranked[:MAX_RESULTS_FOR_PROMPT]


def _format_results_for_prompt(results: list[ContentResult]) -> str:
    """Serialize classified results for inclusion in the prompt."""
    if not results:
        return "No classified results available."

    lines = []
    for i, result in enumerate(results, start=1):
        metrics = result.raw_metrics or {}
        views = metrics.get("views", metrics.get("upvotes", 0))
        likes = metrics.get("likes", metrics.get("comments", 0))

        lines.append(
            f"{i}. [{result.platform.upper()}] {result.title}\n"
            f"   Classification: {result.classification}\n"
            f"   Engagement: {result.engagement_score:,.0f} (views/upvotes: {views:,}, likes/comments: {likes:,})\n"
            f"   Source: {result.source}\n"
            f"   URL: {result.url}"
        )
    return "\n".join(lines)


def _build_prompt(
    profile: ChannelProfile,
    topic: str,
    results: list[ContentResult],
) -> str:
    """Build the AI prompt from channel profile, topic, and top results."""
    selected = _select_results_for_prompt(results)
    results_block = _format_results_for_prompt(selected)

    # Count classifications for context
    trending_count = sum(1 for r in results if r.classification == "trending")
    popular_count = sum(1 for r in results if r.classification == "popular")
    underrated_count = sum(1 for r in results if r.classification == "underrated")

    return f"""You are an expert YouTube content strategist. Your job is to help a specific creator decide what to make next based on real data from their niche.

Analyze the channel profile, searched topic, and classified content results below.
Return ONLY a raw JSON object (no markdown, no code fences) with exactly these keys:

{{
  "summary": "3-4 sentences analyzing what is happening around this topic right now. Reference specific patterns from the results — which types of content are trending vs popular vs underrated, what angles are saturated, and what the engagement patterns tell you about audience interest. Be analytical, not descriptive.",
  "content_angles": [
    "4-5 specific, actionable content angles for THIS channel. Each angle must: (a) reference a specific result or pattern from the data, (b) explain why it fits this channel's niche and audience, (c) describe how to execute it differently from what competitors are doing. Example: 'Create a "Why nobody talks about [underrated topic X]" video — r/technology is buzzing about it (see result #3, 500 upvotes) but no YouTube channel in your niche has covered it. Your concise review style would make this a 8-10 min video with a provocative thumbnail.'"
  ],
  "content_gap": "Identify one clear content gap you see in the results — an angle, topic, or format that competitors and trending content have NOT covered but the audience clearly wants. Be specific about what the gap is and how to fill it. Use null only if the results are too sparse to identify a gap."
}}

Channel profile:
- Title: {profile.title}
- Niche: {profile.niche}
- Topics: {json.dumps(profile.topics)}
- Content style: {profile.content_style}
- Target audience: {profile.target_audience}
- AI summary: {profile.ai_summary}
- Recent video titles: {json.dumps(profile.recent_video_titles[:8])}

Searched topic: {topic}

Result distribution: {trending_count} trending, {popular_count} popular, {underrated_count} underrated

Top classified results:
{results_block}

Critical requirements:
- Do NOT give generic advice. Every recommendation must reference specific data from the results above.
- Content angles must be specific enough that the creator could start scripting the video today.
- If most results are "popular" (old but high engagement), focus on how to update or improve on those proven formats.
- If results are "trending" (recent + high velocity), focus on how to jump on the trend quickly with a unique angle.
- If results are "underrated" (high ratio, low reach), focus on how to take an underexposed topic and make it mainstream.
"""


def _parse_insight_response(text: str) -> TopicInsight:
    """Parse and validate an AI JSON response into a TopicInsight."""
    cleaned = _strip_markdown_fences(text)
    data = json.loads(cleaned)

    if not isinstance(data, dict):
        raise ValueError("Response is not a JSON object")

    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Missing or invalid summary")

    angles = data.get("content_angles")
    if not isinstance(angles, list) or not (3 <= len(angles) <= 6):
        raise ValueError("content_angles must be a list of 3-6 strings")
    if not all(isinstance(angle, str) and angle.strip() for angle in angles):
        raise ValueError("Each content angle must be a non-empty string")

    content_gap = data.get("content_gap")
    if content_gap is not None and not isinstance(content_gap, str):
        raise ValueError("content_gap must be a string or null")
    if isinstance(content_gap, str) and not content_gap.strip():
        content_gap = None

    return TopicInsight(
        summary=summary.strip(),
        content_angles=[angle.strip() for angle in angles],
        content_gap=content_gap.strip() if content_gap else None,
    )


def _fallback_insight() -> TopicInsight:
    return TopicInsight(
        summary=FALLBACK_SUMMARY,
        content_angles=[],
        content_gap=None,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_insights(
    profile: ChannelProfile,
    topic: str,
    results: list[ContentResult],
) -> TopicInsight:
    """Generate topic-specific insights and content angles for *profile*."""
    prompt = _build_prompt(profile, topic, results)

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            response = generate_ai_response(
                prompt=prompt,
                complexity=ComplexityLevel.MEDIUM,
            )
            return _parse_insight_response(response)
        except Exception as exc:
            last_error = exc
            logger.warning(
                "AI insight generation failed (attempt %d/%d): %s",
                attempt,
                MAX_RETRY_ATTEMPTS,
                exc,
            )

    logger.warning("All AI insight attempts failed: %s", last_error)
    return _fallback_insight()
