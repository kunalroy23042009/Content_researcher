"""Tests for Phase 7 — content classification."""

from datetime import datetime, timedelta, timezone

from app.classifier import (
    POPULAR_TOP_PERCENT,
    TRENDING_ENGAGEMENT_PERCENTILE,
    TRENDING_MAX_AGE_HOURS,
    UNDERRATED_MIN_ENGAGEMENT,
    UNDERRATED_TOP_PERCENT,
    classify_results,
)
from app.models import ContentResult


NOW = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)


def _result(
    *,
    title: str,
    engagement: float,
    hours_ago: float,
    platform: str = "youtube",
    raw_metrics: dict | None = None,
    source: str = "Channel",
) -> ContentResult:
    metrics = raw_metrics or (
        {"views": int(engagement), "likes": 10}
        if platform == "youtube"
        else {"upvotes": int(engagement), "comments": 5}
    )
    return ContentResult(
        platform=platform,  # type: ignore[arg-type]
        title=title,
        url=f"https://example.com/{title}",
        engagement_score=engagement,
        published_at=NOW - timedelta(hours=hours_ago),
        source=source,
        raw_metrics=metrics,
    )


def test_every_result_gets_a_classification():
    results = [
        _result(title=f"v{i}", engagement=float(i * 100), hours_ago=100 + i)
        for i in range(1, 11)
    ]
    classified = classify_results(results, now=NOW)

    assert len(classified) == 10
    assert all(r.classification is not None for r in classified)
    assert all(
        r.classification in {"trending", "popular", "underrated", "none"}
        for r in classified
    )


def test_recent_high_engagement_is_trending_not_popular():
    """A 2-day-old high-engagement video should be trending (priority over popular)."""
    results = [
        _result(title="fresh_hit", engagement=10_000, hours_ago=48),
        _result(title="old_hit", engagement=9_500, hours_ago=200),
        _result(title="mid_a", engagement=1_000, hours_ago=150),
        _result(title="mid_b", engagement=900, hours_ago=160),
        _result(title="low_a", engagement=100, hours_ago=300),
        _result(title="low_b", engagement=80, hours_ago=400),
        _result(title="low_c", engagement=50, hours_ago=500),
        _result(title="low_d", engagement=40, hours_ago=600),
    ]
    classified = classify_results(results, now=NOW)
    by_title = {r.title: r.classification for r in classified}

    assert by_title["fresh_hit"] == "trending"
    assert by_title["old_hit"] == "popular"


def test_trending_requires_both_recency_and_high_engagement():
    results = [
        _result(title="fresh_but_quiet", engagement=50, hours_ago=24),
        _result(title="old_and_loud", engagement=5_000, hours_ago=200),
        _result(title="a", engagement=4_000, hours_ago=180),
        _result(title="b", engagement=3_000, hours_ago=170),
        _result(title="c", engagement=2_000, hours_ago=160),
        _result(title="d", engagement=1_000, hours_ago=150),
        _result(title="e", engagement=500, hours_ago=140),
        _result(title="f", engagement=200, hours_ago=130),
    ]
    classified = classify_results(results, now=NOW)
    by_title = {r.title: r.classification for r in classified}

    assert by_title["fresh_but_quiet"] != "trending"
    assert by_title["old_and_loud"] == "popular"


def test_underrated_uses_engagement_to_audience_ratio():
    """High views relative to a small channel beats a huge channel with more views."""
    results = [
        # Popular anchors (old, high engagement)
        _result(
            title="mega",
            engagement=100_000,
            hours_ago=200,
            raw_metrics={"views": 100_000, "likes": 1, "channel_subscriber_count": 5_000_000},
        ),
        _result(
            title="mega2",
            engagement=90_000,
            hours_ago=210,
            raw_metrics={"views": 90_000, "likes": 1, "channel_subscriber_count": 4_000_000},
        ),
        # Mid pack
        _result(
            title="mid1",
            engagement=5_000,
            hours_ago=180,
            raw_metrics={"views": 5_000, "likes": 1, "channel_subscriber_count": 500_000},
        ),
        _result(
            title="mid2",
            engagement=4_000,
            hours_ago=190,
            raw_metrics={"views": 4_000, "likes": 1, "channel_subscriber_count": 400_000},
        ),
        _result(
            title="mid3",
            engagement=3_000,
            hours_ago=200,
            raw_metrics={"views": 3_000, "likes": 1, "channel_subscriber_count": 300_000},
        ),
        # Small channel punching above its weight → underrated
        _result(
            title="sleeper",
            engagement=2_500,
            hours_ago=220,
            raw_metrics={"views": 2_500, "likes": 1, "channel_subscriber_count": 1_000},
        ),
        _result(
            title="low1",
            engagement=200,
            hours_ago=250,
            raw_metrics={"views": 200, "likes": 1, "channel_subscriber_count": 50_000},
        ),
        _result(
            title="low2",
            engagement=100,
            hours_ago=260,
            raw_metrics={"views": 100, "likes": 1, "channel_subscriber_count": 40_000},
        ),
    ]
    classified = classify_results(results, now=NOW)
    by_title = {r.title: r.classification for r in classified}

    assert by_title["mega"] == "popular"
    assert by_title["sleeper"] == "underrated"
    # Underrated must never override popular
    assert by_title["mega"] != "underrated"


def test_underrated_excludes_already_popular():
    results = [
        _result(
            title="popular_high_ratio",
            engagement=50_000,
            hours_ago=300,
            raw_metrics={"views": 50_000, "channel_subscriber_count": 100},
        ),
        _result(title="a", engagement=1_000, hours_ago=200),
        _result(title="b", engagement=900, hours_ago=200),
        _result(title="c", engagement=800, hours_ago=200),
        _result(title="d", engagement=100, hours_ago=200),
        _result(title="e", engagement=50, hours_ago=200),
    ]
    classified = classify_results(results, now=NOW)
    by_title = {r.title: r.classification for r in classified}

    assert by_title["popular_high_ratio"] == "popular"


def test_empty_input_returns_empty():
    assert classify_results([]) == []


def test_thresholds_are_named_constants():
    assert TRENDING_MAX_AGE_HOURS == 72
    assert TRENDING_ENGAGEMENT_PERCENTILE == 75
    assert POPULAR_TOP_PERCENT == 20
    assert UNDERRATED_TOP_PERCENT == 15
    assert UNDERRATED_MIN_ENGAGEMENT == 10.0


def test_spot_check_five_results_intuitive_labels():
    """Manual-style spot check against raw metrics (acceptance criterion)."""
    results = [
        # 1. 2-day-old, top engagement → trending
        _result(title="1_fresh_viral", engagement=20_000, hours_ago=48),
        # 2. Old evergreen high engagement → popular
        _result(title="2_evergreen", engagement=18_000, hours_ago=720),
        # 3. Fresh but low engagement → not trending, below underrated floor
        _result(title="3_fresh_quiet", engagement=5, hours_ago=12),
        # 4. Modest views, tiny channel → underrated candidate
        _result(
            title="4_sleeper",
            engagement=5_000,
            hours_ago=400,
            raw_metrics={"views": 5_000, "channel_subscriber_count": 500},
        ),
        # 5. Low everything → none
        _result(
            title="5_noise",
            engagement=30,
            hours_ago=500,
            raw_metrics={"views": 30, "channel_subscriber_count": 100_000},
        ),
        # Fillers: decent views but huge channels → low engagement/audience ratio
        _result(
            title="f1",
            engagement=3_000,
            hours_ago=300,
            raw_metrics={"views": 3_000, "channel_subscriber_count": 2_000_000},
        ),
        _result(
            title="f2",
            engagement=2_500,
            hours_ago=310,
            raw_metrics={"views": 2_500, "channel_subscriber_count": 1_500_000},
        ),
        _result(
            title="f3",
            engagement=2_000,
            hours_ago=320,
            raw_metrics={"views": 2_000, "channel_subscriber_count": 1_000_000},
        ),
        _result(
            title="f4",
            engagement=1_500,
            hours_ago=330,
            raw_metrics={"views": 1_500, "channel_subscriber_count": 800_000},
        ),
        _result(
            title="f5",
            engagement=1_000,
            hours_ago=340,
            raw_metrics={"views": 1_000, "channel_subscriber_count": 500_000},
        ),
    ]
    classified = classify_results(results, now=NOW)
    by_title = {r.title: r for r in classified}

    assert by_title["1_fresh_viral"].classification == "trending"
    assert by_title["2_evergreen"].classification == "popular"
    assert by_title["3_fresh_quiet"].classification == "none"
    assert by_title["4_sleeper"].classification == "underrated"
    assert by_title["5_noise"].classification == "none"
