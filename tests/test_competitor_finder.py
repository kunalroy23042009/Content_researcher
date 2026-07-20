"""Tests for Phase 5 — competitor discovery."""

from unittest.mock import MagicMock, patch

from app.competitor_finder import find_competitors, generate_search_queries
from app.models import ChannelProfile, CompetitorChannel


def _sample_profile(**overrides) -> ChannelProfile:
    defaults = {
        "channel_id": "UCsource1234567890123456",
        "title": "Tech Tips Daily",
        "description": "Short tech tutorials for beginners.",
        "subscriber_count": 50_000,
        "video_count": 120,
        "view_count": 2_000_000,
        "recent_video_titles": ["Best budget laptop 2025", "Windows tips"],
        "niche": "tech tutorials",
        "topics": ["laptops", "Windows", "budget tech"],
        "content_style": "concise how-to videos",
        "target_audience": "beginner PC users",
        "ai_summary": "A channel teaching practical tech skills.",
    }
    defaults.update(overrides)
    return ChannelProfile(**defaults)


def test_generate_search_queries_uses_gemini_response():
    profile = _sample_profile()
    mock_response = MagicMock()
    mock_response.text = '["budget laptop review", "windows tips for beginners"]'

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("app.competitor_finder._get_gemini_client", return_value=mock_client):
        queries = generate_search_queries(profile)

    assert queries == ["budget laptop review", "windows tips for beginners"]


def test_generate_search_queries_falls_back_when_gemini_fails():
    profile = _sample_profile()

    with patch("app.competitor_finder._get_gemini_client", side_effect=RuntimeError("offline")):
        queries = generate_search_queries(profile)

    assert "tech tutorials" in queries
    assert "laptops" in queries
    assert "channels like Tech Tips Daily" in queries


def test_find_competitors_excludes_source_and_returns_ranked_results():
    profile = _sample_profile(subscriber_count=10_000)
    source_id = profile.channel_id

    search_responses = [
        {
            "items": [
                {"snippet": {"channelId": source_id}},
                {"snippet": {"channelId": "UCcompetitor111111111111111"}},
                {"snippet": {"channelId": "UCcompetitor222222222222222"}},
            ]
        },
        {
            "items": [
                {"snippet": {"channelId": "UCcompetitor111111111111111"}},
                {"snippet": {"channelId": "UCcompetitor333333333333333"}},
            ]
        },
    ]

    channel_response = {
        "items": [
            {
                "id": "UCcompetitor111111111111111",
                "snippet": {"title": "Close Competitor"},
                "statistics": {"subscriberCount": "12000"},
            },
            {
                "id": "UCcompetitor222222222222222",
                "statistics": {"subscriberCount": "1000000"},
                "snippet": {"title": "Huge Channel"},
            },
            {
                "id": "UCcompetitor333333333333333",
                "snippet": {"title": "Mid Competitor"},
                "statistics": {"subscriberCount": "15000"},
            },
        ]
    }

    mock_youtube = MagicMock()
    mock_youtube.search.return_value.list.return_value.execute.side_effect = search_responses
    mock_youtube.channels.return_value.list.return_value.execute.return_value = channel_response

    with (
        patch("app.competitor_finder.generate_search_queries", return_value=["q1", "q2"]),
        patch("app.competitor_finder._build_youtube_client", return_value=mock_youtube),
    ):
        competitors = find_competitors(profile, exclude_channel_id=source_id)

    assert len(competitors) == 3
    assert all(isinstance(c, CompetitorChannel) for c in competitors)
    assert all(c.channel_id != source_id for c in competitors)
    assert all(c.title and c.relevance_note for c in competitors)

    # Closest subscriber count should rank first.
    assert competitors[0].channel_id == "UCcompetitor111111111111111"
    assert competitors[0].subscriber_count == 12_000


def test_find_competitors_returns_fewer_than_ten_without_crashing():
    profile = _sample_profile()
    search_response = {
        "items": [
            {"snippet": {"channelId": "UConlyone1111111111111111"}},
        ]
    }
    channel_response = {
        "items": [
            {
                "id": "UConlyone1111111111111111",
                "snippet": {"title": "Solo Competitor"},
                "statistics": {"subscriberCount": "8000"},
            }
        ]
    }

    mock_youtube = MagicMock()
    mock_youtube.search.return_value.list.return_value.execute.return_value = search_response
    mock_youtube.channels.return_value.list.return_value.execute.return_value = channel_response

    with (
        patch("app.competitor_finder.generate_search_queries", return_value=["one query"]),
        patch("app.competitor_finder._build_youtube_client", return_value=mock_youtube),
    ):
        competitors = find_competitors(profile, exclude_channel_id=profile.channel_id)

    assert len(competitors) == 1
    assert competitors[0].title == "Solo Competitor"


def test_find_competitors_returns_empty_list_when_no_candidates():
    profile = _sample_profile()

    mock_youtube = MagicMock()
    mock_youtube.search.return_value.list.return_value.execute.return_value = {"items": []}

    with (
        patch("app.competitor_finder.generate_search_queries", return_value=["empty query"]),
        patch("app.competitor_finder._build_youtube_client", return_value=mock_youtube),
    ):
        competitors = find_competitors(profile, exclude_channel_id=profile.channel_id)

    assert competitors == []
