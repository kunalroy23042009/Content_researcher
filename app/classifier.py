"""Classifier — labels content as trending, popular, or underrated.

Improved classification using engagement velocity (engagement per hour since publish)
combined with recency to identify trending content. Popular = high absolute engagement.
Underrated = high engagement relative to audience size but low absolute reach.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from app.models import ContentResult

# ---------------------------------------------------------------------------
# Tunable thresholds
# ---------------------------------------------------------------------------

TRENDING_MAX_AGE_HOURS = 168          # 7 days (was 72h — too strict)
TRENDING_MIN_ENGAGEMENT = 100.0       # floor to avoid noise
TRENDING_VELOCITY_PERCENTILE = 60    # top 40% by velocity → trending candidate

POPULAR_TOP_PERCENT = 25             # top 25% by engagement → popular
POPULAR_MIN_ENGAGEMENT = 500.0       # must have meaningful reach

UNDERRATED_TOP_PERCENT = 30          # top 30% by engagement ratio → underrated
UNDERRATED_MIN_ENGAGEMENT = 5.0      # floor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _percentile(values: list[float], pct: float) -> float:
    """Return the *pct*-th percentile of *values* (linear interpolation)."""
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
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _age_hours(published_at: datetime, now: datetime) -> float:
    delta = _ensure_aware(now) - _ensure_aware(published_at)
    return max(delta.total_seconds() / 3600.0, 0.0)


def _engagement_velocity(result: ContentResult, now: datetime) -> float:
    """Engagement per hour since publish — higher = faster-growing.

    Returns 0 for content published in the future or with 0 engagement.
    """
    age_h = _age_hours(result.published_at, now)
    if age_h < 1:  # Less than 1 hour old — treat as 1h to avoid div-by-zero explosion
        age_h = 1.0
    return result.engagement_score / age_h


def _engagement_ratio(result: ContentResult) -> float | None:
    """Engagement relative to audience size, or None if unavailable."""
    metrics = result.raw_metrics or {}

    if result.platform == "youtube":
        engagement = float(metrics.get("views", result.engagement_score))
        audience = metrics.get("channel_subscriber_count") or metrics.get("subscriber_count")
    else:
        engagement = float(metrics.get("upvotes", result.engagement_score))
        audience = metrics.get("subreddit_subscriber_count") or metrics.get("subscribers")

    if audience is not None and float(audience) > 0:
        return engagement / float(audience)

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

    Classification priority: trending → popular → underrated → none.

    **Trending**: Published within 7 days AND has high engagement velocity
    (engagement per hour) relative to the set. This catches recently-published
    content that is gaining traction fast.

    **Popular**: High absolute engagement (top 25% of the set) regardless of age.
    This catches established, well-performing content.

    **Underrated**: High engagement-to-audience ratio but low absolute reach.
    This catches content that punches above its weight in small channels/subreddits.
    """
    if not results:
        return []

    now = now or datetime.now(timezone.utc)

    # Compute velocity for all results
    velocities = [_engagement_velocity(r, now) for r in results]
    scores = [r.engagement_score for r in results]

    # Thresholds
    trending_velocity_floor = _percentile(
        [v for v in velocities if v > 0],
        TRENDING_VELOCITY_PERCENTILE,
    )
    popular_floor = _percentile(scores, 100 - POPULAR_TOP_PERCENT)

    # Compute ratios for underrated
    ratios: list[float | None] = [_engagement_ratio(r) for r in results]

    labeled: list[ContentResult] = []
    pending_underrated: list[tuple[int, float]] = []

    for i, result in enumerate(results):
        age_h = _age_hours(result.published_at, now)
        velocity = velocities[i]

        # Trending: recent + high velocity
        is_trending = (
            age_h <= TRENDING_MAX_AGE_HOURS
            and result.engagement_score >= TRENDING_MIN_ENGAGEMENT
            and velocity >= trending_velocity_floor
        )

        # Popular: high absolute engagement (regardless of age)
        is_popular = result.engagement_score >= max(popular_floor, POPULAR_MIN_ENGAGEMENT)

        if is_trending:
            classification = "trending"
        elif is_popular:
            classification = "popular"
        else:
            classification = "none"
            ratio = ratios[i]
            if ratio is not None and ratio > 0:
                pending_underrated.append((i, ratio))

        labeled.append(result.model_copy(update={"classification": classification}))

    # Underrated: top UNDERRATED_TOP_PERCENT of ratios among non-trending/non-popular
    if pending_underrated:
        ratio_values = [r for _, r in pending_underrated]
        underrated_floor = _percentile(ratio_values, 100 - UNDERRATED_TOP_PERCENT)
        for idx, ratio in pending_underrated:
            if ratio >= underrated_floor:
                labeled[idx] = labeled[idx].model_copy(
                    update={"classification": "underrated"}
                )

    return labeled
