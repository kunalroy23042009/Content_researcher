"""Shared test fixtures for Creator Content Radar tests."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.models import ChannelProfile, ContentResult, TopicInsight


NOW = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_channel_profile() -> ChannelProfile:
    return ChannelProfile(
        channel_id="UCtest1234567890123456789",
        title="Test Tech Channel",
        description="A test channel about technology.",
        subscriber_count=50_000,
        video_count=120,
        view_count=5_000_000,
        recent_video_titles=["Best laptop 2025", "Phone review", "Gadget guide"],
        niche="tech reviews",
        topics=["laptops", "phones", "gadgets"],
        content_style="concise reviews",
        target_audience="tech enthusiasts",
        ai_summary="A channel focused on tech reviews.",
        average_views_per_video=41666.0,
        engagement_rate=4.5,
        channel_tier="Mid-Tier",
        upload_frequency="weekly",
        growth_potential="high",
        content_recommendations=["More shorts", "Comparison videos"],
        optimization_tips=["Better thumbnails", "SEO titles"],
    )


@pytest.fixture
def sample_content_results() -> list[ContentResult]:
    return [
        ContentResult(
            platform="youtube",
            title="Trending Tech Video",
            url="https://www.youtube.com/watch?v=test1",
            engagement_score=50000,
            published_at=NOW,
            source="Big Tech Channel",
            raw_metrics={"views": 50000, "likes": 2000},
            classification="trending",
        ),
        ContentResult(
            platform="youtube",
            title="Popular Old Video",
            url="https://www.youtube.com/watch?v=test2",
            engagement_score=1000000,
            published_at=NOW,
            source="Mega Channel",
            raw_metrics={"views": 1000000, "likes": 50000},
            classification="popular",
        ),
        ContentResult(
            platform="reddit",
            title="Underrated Reddit Post",
            url="https://reddit.com/r/tech/comments/test3",
            engagement_score=500,
            published_at=NOW,
            source="r/technology",
            raw_metrics={"upvotes": 300, "comments": 67},
            classification="underrated",
        ),
    ]


@pytest.fixture
def sample_topic_insight() -> TopicInsight:
    return TopicInsight(
        summary="Tech content is trending with focus on AI and laptops.",
        content_angles=[
            "Create a comparison video of top 5 laptops",
            "Review the latest AI-powered gadgets",
            "Make a beginner's guide to choosing tech",
        ],
        content_gap="No one is covering budget AI laptops under $500",
    )


@pytest.fixture
def mock_youtube_client():
    """Mock YouTube Data API client."""
    client = MagicMock()

    # Channel resolution
    channel_response = {
        "items": [
            {
                "id": "UCtest1234567890123456789",
                "snippet": {
                    "title": "Test Tech Channel",
                    "description": "A test channel about technology.",
                },
                "statistics": {
                    "subscriberCount": "50000",
                    "videoCount": "120",
                    "viewCount": "5000000",
                },
            }
        ]
    }
    client.channels().list().execute.return_value = channel_response

    # Search results
    search_response = {
        "items": [
            {
                "id": {"videoId": f"vid{i}"},
                "snippet": {
                    "title": f"Video {i}",
                    "channelTitle": "Test Tech Channel",
                    "publishedAt": "2025-06-15T12:00:00Z",
                },
            }
            for i in range(15)
        ]
    }
    client.search().list().execute.return_value = search_response

    # Video stats
    video_response = {
        "items": [
            {
                "id": f"vid{i}",
                "statistics": {"viewCount": str(10000 * i), "likeCount": str(500 * i)},
                "snippet": {"title": f"Video {i}", "channelTitle": "Test Tech Channel"},
            }
            for i in range(10)
        ]
    }
    client.videos().list().execute.return_value = video_response

    return client


@pytest.fixture
def mock_gemini_client():
    """Mock Gemini AI client."""
    client = MagicMock()
    response = MagicMock()
    response.text = json.dumps(
        {
            "niche": "tech reviews",
            "topics": ["laptops", "phones"],
            "content_style": "concise",
            "target_audience": "tech enthusiasts",
            "ai_summary": "A tech review channel.",
            "upload_frequency": "weekly",
            "growth_potential": "high",
            "content_recommendations": ["More shorts"],
            "optimization_tips": ["Better thumbnails"],
        }
    )
    client.models.generate_content.return_value = response
    return client


@pytest.fixture
def mock_reddit_client():
    """Mock Reddit/PRAW client."""
    client = MagicMock()
    return client


@pytest.fixture
def test_db():
    """Create an in-memory test database."""
    from app.db import init_db, reset_engine, DB_DIR
    import os

    # Use a temp DB for tests
    os.environ["DATABASE_URL"] = "sqlite:///./data/test_cache.db"
    reset_engine()
    init_db()
    yield
    reset_engine()
    # Cleanup
    test_db_path = DB_DIR / "test_cache.db"
    if test_db_path.exists():
        test_db_path.unlink()


@pytest.fixture
def client():
    """FastAPI TestClient with mocked external services."""
    # We'll mock external APIs at the endpoint level in individual tests
    from app.main import app
    return TestClient(app)


@pytest.fixture
def auth_token():
    """Create a test JWT token."""
    from app.auth import create_access_token
    return create_access_token({"sub": "test@example.com"})
