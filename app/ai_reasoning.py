"""AI reasoning — generates content angle suggestions using multiple AI providers.

Phase 8 implementation.  Turns a classified topic feed plus channel profile into
actionable ``TopicInsight`` recommendations with provider fallback.
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
    """Remove optional ```json fences from a model response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _select_results_for_prompt(results: list[ContentResult]) -> list[ContentResult]:
    """Pick the top results to include in the Gemini prompt (up to 15)."""
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
        lines.append(
            f"{i}. [{result.platform}] {result.title}\n"
            f"   classification: {result.classification}\n"
            f"   engagement_score: {result.engagement_score:,.0f}\n"
            f"   source: {result.source}"
        )
    return "\n".join(lines)


def _build_prompt(
    profile: ChannelProfile,
    topic: str,
    results: list[ContentResult],
) -> str:
    """Build the Gemini prompt from channel profile, topic, and top results."""
    selected = _select_results_for_prompt(results)
    results_block = _format_results_for_prompt(selected)

    return f"""You are a YouTube content strategist helping a specific creator decide what to make next.

Analyze the channel profile, searched topic, and classified content results below.
Return ONLY a JSON object with exactly these keys (no markdown, no code fences):
{{
  "summary": "<2-3 sentences on what is happening around this topic right now>",
  "content_angles": [
    "<specific actionable angle 1 tailored to this channel>",
    "<specific actionable angle 2 tailored to this channel>",
    "<specific actionable angle 3 tailored to this channel>"
  ],
  "content_gap": "<one clearly unclaimed angle you see in the results, or null if none>"
}}

Requirements:
- Reference actual result titles or patterns from the results when possible.
- Content angles must be specific to THIS channel's niche, tone, and format — not generic advice.
- Provide exactly 3 content_angles strings.
- content_gap should identify an opportunity competitors/results have not claimed; use null if unclear.

Channel profile:
- Title: {profile.title}
- Niche: {profile.niche}
- Topics: {json.dumps(profile.topics)}
- Content style: {profile.content_style}
- Target audience: {profile.target_audience}
- AI summary: {profile.ai_summary}
- Recent video titles: {json.dumps(profile.recent_video_titles[:8])}

Searched topic: {topic}

Top classified results:
{results_block}
"""


def _parse_insight_response(text: str) -> TopicInsight:
    """Parse and validate a Gemini JSON response into a ``TopicInsight``."""
    cleaned = _strip_markdown_fences(text)
    data = json.loads(cleaned)

    if not isinstance(data, dict):
        raise ValueError("Response is not a JSON object")

    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Missing or invalid summary")

    angles = data.get("content_angles")
    if not isinstance(angles, list) or len(angles) != 3:
        raise ValueError("content_angles must be a list of exactly 3 strings")
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
    """Return a safe fallback when Gemini output cannot be parsed."""
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
    """Generate topic-specific insights and content angles for *profile*.

    Sends the channel niche profile, topic, and top classified results to AI.
    Uses provider fallback system and retries on malformed output.
    """
    prompt = _build_prompt(profile, topic, results)

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            response = generate_ai_response(
                prompt=prompt,
                complexity=ComplexityLevel.MEDIUM,  # Topic insights are medium complexity
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
