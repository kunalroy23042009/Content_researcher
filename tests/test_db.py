"""Tests for Phase 9 — SQLite caching and database."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.channel_analyzer import analyze_channel
from app.db import (
    get_cached_channel_profile,
    get_cached_topic_search,
    init_db,
    reset_engine,
    save_channel_profile,
    save_topic_search,
)
from app.models import ChannelProfile, ContentResult, TopicInsight
from app.topic_search import search_topic_with_insights


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Use an isolated SQLite file for each test."""
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr("app.db.DB_PATH", db_path)
    monkeypatch.setattr("app.db.DB_DIR", tmp_path)
    reset_engine()
    init_db()
    yield db_path
    reset_engine()


def _profile(channel_id: str = "UCtest123456789012345678") -> ChannelProfile:
    return ChannelProfile(
        channel_id=channel_id,
        title="Test Channel",
        description="A test channel",
        subscriber_count=10_000,
        video_count=50,
        view_count=500_000,
        recent_video_titles=["Video A"],
        niche="testing",
        topics=["pytest"],
        content_style="concise",
        target_audience="developers",
        ai_summary="Test summary.",
    )


def _content_result(title: str = "Result") -> ContentResult:
    return ContentResult(
        platform="youtube",
        title=title,
        url="https://www.youtube.com/watch?v=abc",
        engagement_score=1_000.0,
        published_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        source="Test Channel",
        raw_metrics={"views": 1000, "likes": 10},
        classification="trending",
    )


def _insight() -> TopicInsight:
    return TopicInsight(
        summary="Topic is active.",
        content_angles=["Angle 1", "Angle 2", "Angle 3"],
        content_gap="Unclaimed gap.",
    )


def test_init_db_creates_sqlite_file(temp_db):
    assert temp_db.exists()
    assert temp_db.stat().st_size > 0


def test_save_and_get_channel_profile(temp_db):
    profile = _profile()
    save_channel_profile(profile, url="https://www.youtube.com/channel/UCtest123456789012345678")

    cached = get_cached_channel_profile(profile.channel_id)
    assert cached is not None
    assert cached.title == "Test Channel"
    assert cached.niche == "testing"


def test_save_and_get_topic_search(temp_db):
    profile = _profile()
    save_channel_profile(profile, url="https://www.youtube.com/channel/UCtest123456789012345678")

    results = [_content_result()]
    insight = _insight()
    save_topic_search(profile.channel_id, "budget laptop", results, insight)

    cached = get_cached_topic_search(profile.channel_id, "budget laptop")
    assert cached is not None
    cached_results, cached_insight = cached
    assert len(cached_results) == 1
    assert cached_results[0].title == "Result"
    assert cached_insight.summary == "Topic is active."


def test_analyze_channel_uses_cache_on_second_call(temp_db):
    profile = _profile()
    channel_url = "https://www.youtube.com/channel/UCtest123456789012345678"

    with patch("app.channel_analyzer._analyze_channel_live", return_value=profile) as live_mock:
        first = analyze_channel(channel_url)
        second = analyze_channel(channel_url)

    assert live_mock.call_count == 1
    assert first.channel_id == second.channel_id
    assert second.title == "Test Channel"


def test_search_topic_with_insights_uses_cache_on_second_call(temp_db):
    profile = _profile()
    save_channel_profile(profile, url="https://www.youtube.com/channel/UCtest123456789012345678")

    classified = [_content_result("Cached result")]
    insight = _insight()

    with (
        patch("app.topic_search.search_topic", return_value=classified) as search_mock,
        patch(
            "app.ai_reasoning.generate_insights",
            return_value=insight,
        ) as insight_mock,
        patch(
            "app.classifier.classify_results",
            side_effect=lambda results: results,
        ),
    ):
        first_results, first_insight = search_topic_with_insights(
            profile,
            "budget laptop",
            competitor_channel_ids=[],
            subreddits=None,
        )
        second_results, second_insight = search_topic_with_insights(
            profile,
            "budget laptop",
            competitor_channel_ids=[],
            subreddits=None,
        )

    assert search_mock.call_count == 1
    assert insight_mock.call_count == 1
    assert first_results[0].title == "Cached result"
    assert second_results[0].title == "Cached result"
    assert second_insight.summary == first_insight.summary


def test_expired_cache_triggers_live_call(temp_db):
    profile = _profile()
    channel_url = "https://www.youtube.com/channel/UCtest123456789012345678"

    with patch("app.channel_analyzer._analyze_channel_live", return_value=profile) as live_mock:
        analyze_channel(channel_url, max_age_hours=24)
        analyze_channel(channel_url, max_age_hours=0)

    assert live_mock.call_count == 2
