"""
Tests for Pydantic models.
"""
import pytest
from datetime import datetime, timezone
from app.models import ChannelProfile, ContentResult, CompetitorChannel, TopicInsight, VideoPerformance


def test_channel_profile_defaults():
    profile = ChannelProfile(
        channel_id="UC123",
        title="Test Channel",
        description="A test channel",
        subscriber_count=10_000,
        video_count=100,
        view_count=500_000,
    )
    assert profile.channel_id == "UC123"
    assert profile.niche == ""
    assert profile.topics == []
    assert profile.content_recommendations == []


def test_content_result_defaults():
    result = ContentResult(
        platform="youtube",
        title="Test Video",
        url="https://youtube.com/watch?v=test",
        engagement_score=1000.0,
        published_at=datetime.now(timezone.utc),
        classification="trending",
    )
    assert result.platform == "youtube"
    assert result.raw_metrics == {}


def test_competitor_channel():
    comp = CompetitorChannel(
        channel_id="UC456",
        title="Competitor Channel",
        description="A competitor",
        subscriber_count=50_000,
        thumbnail_url="",
        similarity_score=0.8,
    )
    assert comp.similarity_score == 0.8


def test_video_performance():
    vp = VideoPerformance(
        title="My Best Video",
        video_id="abc123",
        views=100_000,
        likes=5000,
        comments=300,
        performance_ratio=2.5,
    )
    assert vp.performance_ratio == 2.5


def test_topic_insight():
    from datetime import datetime, timezone
    insight = TopicInsight(
        topic="python tutorial",
        results=[],
        ai_summary="Python tutorials are trending.",
        content_angles=["Beginner Python", "Advanced Python"],
        recommended_format="tutorial",
        competition_level="medium",
    )
    assert insight.topic == "python tutorial"
    assert len(insight.content_angles) == 2
