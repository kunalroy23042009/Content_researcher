"""Classifier — labels content as trending, popular, or underrated.

Phase 7 implementation.  Pure heuristics relative to the current result set —
no external API calls.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from app.models import ContentResult

# ---------------------------------------------------------------------------
# Tunable thresholds (change these without touching classification logic)
# ---------------------------------------------------------------------------

TRENDING_MAX_AGE_HOURS = 72
TRENDING_ENGAGEMENT_PERCENTILE = 75  # must be above this percentile of the set

POPULAR_TOP_PERCENT = 20  # top 20% by engagement_score → 80th percentile floor

UNDERRATED_TOP_PERCENT = 15  # top 15% by engagement/audience ratio
UNDERRATED_MIN_ENGAGEMENT = 10.0  # floor when audience size is unavailable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _percentile(values: list[float], pct: float) -> float:
    """Return the *pct*-th percentile of *values* (linear interpolation).

    *pct* is in [0, 100].  Returns 0.0 for an empty list.
    """
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]

    ordered = sorted(values)
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _ensure_aware(dt: datetime) -> datetime:
    """Treat naive datetimes as UTC so age comparisons are safe."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _age_hours(published_at: datetime, now: datetime) -> float:
    """Hours between *published_at* and *now* (never negative)."""
    delta = _ensure_aware(now) - _ensure_aware(published_at)
    return max(delta.total_seconds() / 3600.0, 0.0)


def _engagement_ratio(result: ContentResult) -> float | None:
    """Engagement relative to audience size, or ``None`` if below the floor.

    YouTube: views / channel_subscriber_count (when present).
    Reddit:  upvotes / subreddit_subscriber_count (when present).
    Fallback: raw ``engagement_score`` when audience size is missing.
    """
    metrics = result.raw_metrics or {}

    if result.platform == "youtube":
        engagement = float(metrics.get("views", result.engagement_score))
        audience = metrics.get("channel_subscriber_count")
        if audience is None:
            audience = metrics.get("subscriber_count")
    else:
        engagement = float(metrics.get("upvotes", result.engagement_score))
        audience = metrics.get("subreddit_subscriber_count")
        if audience is None:
            audience = metrics.get("subscribers")

    if audience is not None and float(audience) > 0:
        return engagement / float(audience)

    # No audience size — fall back to raw engagement, gated by a floor.
    if result.engagement_score < UNDERRATED_MIN_ENGAGEMENT:
        return None
    return float(result.engagement_score)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_results(
    results: list[ContentResult],
    *,
    now: datetime | None = None,
) -> list[ContentResult]:
    """Label each result as trending, popular, underrated, or none.

    Labels are mutually exclusive and applied in priority order:
    ``trending`` → ``popular`` → ``underrated`` → ``none``.

    Percentile thresholds are computed against *this* result set only.
    """
    if not results:
        return []

    now = now or datetime.now(timezone.utc)
    scores = [r.engagement_score for r in results]
    trending_floor = _percentile(scores, TRENDING_ENGAGEMENT_PERCENTILE)
    popular_floor = _percentile(scores, 100 - POPULAR_TOP_PERCENT)

    # Pre-compute ratios for underrated (skip results that will already be popular).
    # We still need the full ratio distribution among eligible candidates only after
    # knowing popular/trending — compute ratios for all first, then threshold later.
    ratios: list[float | None] = [_engagement_ratio(r) for r in results]

    labeled: list[ContentResult] = []
    pending_underrated: list[tuple[int, float]] = []  # (index, ratio)

    for i, result in enumerate(results):
        age_h = _age_hours(result.published_at, now)
        is_trending = (
            age_h <= TRENDING_MAX_AGE_HOURS
            and result.engagement_score >= trending_floor
        )
        is_popular = result.engagement_score >= popular_floor

        if is_trending:
            classification = "trending"
        elif is_popular:
            classification = "popular"
        else:
            classification = "none"
            ratio = ratios[i]
            if ratio is not None:
                pending_underrated.append((i, ratio))

        labeled.append(result.model_copy(update={"classification": classification}))

    # Underrated: top UNDERRATED_TOP_PERCENT of ratios among non-trending/non-popular.
    if pending_underrated:
        ratio_values = [r for _, r in pending_underrated]
        underrated_floor = _percentile(ratio_values, 100 - UNDERRATED_TOP_PERCENT)
        for idx, ratio in pending_underrated:
            if ratio >= underrated_floor:
                labeled[idx] = labeled[idx].model_copy(
                    update={"classification": "underrated"}
                )

    return labeled
